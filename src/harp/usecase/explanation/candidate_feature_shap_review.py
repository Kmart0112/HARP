from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from harp.core.explainability import (
    CandidateShapReviewBundle,
    ShapMetricsContext,
    build_candidate_shap_review,
    build_tree_shap_explanation,
    resolve_interaction_feature,
)
from harp.core.training import BinaryDataset
from harp.interface.ports import TrainingRepositoryPort

from .artifact_dataset import (
    ArtifactExplanationDatasetDeps,
    ArtifactExplanationDatasetRequest,
    run_rebuild_artifact_explanation_dataset_usecase,
)


@dataclass(frozen=True)
class CandidateFeatureShapReviewRequest:
    payload: dict[str, Any]
    target_col: str
    candidate_feature: str
    comparison_features: list[str]
    split: str
    held_year_range: tuple[int, int]
    sample_size_cap: int
    metrics_context: ShapMetricsContext
    limit: int | None = None
    where: dict[str, object] | None = None
    df_train: pd.DataFrame | None = None
    random_state: int = 42


@dataclass(frozen=True)
class CandidateFeatureShapReviewDeps:
    training_repository: TrainingRepositoryPort
    mart_table: str


@dataclass(frozen=True)
class CandidateFeatureShapReviewResult:
    df_train: pd.DataFrame
    ds: BinaryDataset
    review: CandidateShapReviewBundle


def run_candidate_feature_shap_review_usecase(
    req: CandidateFeatureShapReviewRequest,
    deps: CandidateFeatureShapReviewDeps,
) -> CandidateFeatureShapReviewResult:
    comparison_features = _validate_review_request(req)
    rebuild_result = run_rebuild_artifact_explanation_dataset_usecase(
        req=ArtifactExplanationDatasetRequest(
            payload=req.payload,
            target_col=req.target_col,
            limit=req.limit,
            where=req.where,
            df_train=req.df_train,
        ),
        deps=ArtifactExplanationDatasetDeps(
            training_repository=deps.training_repository,
            mart_table=deps.mart_table,
        ),
    )
    df_train = _ensure_held_year(rebuild_result.df_train)
    ds = rebuild_result.ds
    split_frames = {
        "train": (ds.X_tr, ds.y_tr),
        "val": (ds.X_val, ds.y_val),
        "test": (ds.X_test, ds.y_test),
    }
    selected_frame, selected_target = split_frames[req.split]
    selected_held_year = pd.to_numeric(df_train.loc[selected_frame.index, "held_year"], errors="raise").astype(int)
    year_min, year_max = int(req.held_year_range[0]), int(req.held_year_range[1])
    selected_mask = (selected_held_year >= year_min) & (selected_held_year <= year_max)
    selected_frame = selected_frame.loc[selected_mask].copy()
    selected_target = selected_target.loc[selected_mask].copy()
    if selected_frame.empty:
        raise ValueError("No rows remain after held_year filtering.")

    sample_cap = max(int(req.sample_size_cap), 1)
    selected_frame, selected_target = _sample_frame(
        feature_frame=selected_frame,
        target=selected_target,
        sample_size_cap=sample_cap,
        random_state=req.random_state,
    )

    model = _resolve_base_model(req.payload)
    explanation = build_tree_shap_explanation(model, selected_frame)
    pred_proba = pd.Series(
        np.asarray(model.predict_proba(selected_frame)[:, 1], dtype=float),
        index=selected_frame.index,
        name="pred_proba",
    )

    interaction_feature = resolve_interaction_feature(
        explanation=explanation,
        candidate_feature=req.candidate_feature,
        comparison_features=comparison_features,
    )
    split_explanations: dict[str, tuple[Any, pd.DataFrame]] = {}
    for split_name, (feature_frame, _) in split_frames.items():
        sampled_frame, _ = _sample_frame(
            feature_frame=feature_frame,
            target=None,
            sample_size_cap=sample_cap,
            random_state=req.random_state,
        )
        if sampled_frame.empty:
            continue
        split_explanations[split_name] = (
            build_tree_shap_explanation(model, sampled_frame),
            sampled_frame,
        )

    year_explanations: dict[int, tuple[Any, pd.DataFrame]] = {}
    yearly_source = _concat_sampled_year_frames(
        split_frames=split_frames,
        df_train=df_train,
        sample_size_cap=sample_cap,
        random_state=req.random_state,
    )
    for held_year, year_frame in yearly_source.groupby("held_year"):
        feature_frame = year_frame.loc[:, ds.feature_names].copy()
        if feature_frame.empty:
            continue
        year_explanations[int(held_year)] = (
            build_tree_shap_explanation(model, feature_frame),
            feature_frame,
        )

    review = build_candidate_shap_review(
        explanation=explanation,
        feature_frame=selected_frame,
        y_true=selected_target,
        pred_proba=pred_proba,
        candidate_feature=req.candidate_feature,
        comparison_features=comparison_features,
        metrics_context=req.metrics_context,
        split_name=req.split,
        held_year_min=year_min,
        held_year_max=year_max,
        split_explanations=split_explanations,
        year_explanations=year_explanations,
        interaction_feature=interaction_feature,
    )
    return CandidateFeatureShapReviewResult(
        df_train=df_train,
        ds=ds,
        review=review,
    )


def _validate_review_request(req: CandidateFeatureShapReviewRequest) -> list[str]:
    if req.split not in {"train", "val", "test"}:
        raise ValueError(f"Unsupported split: {req.split}")
    if not req.candidate_feature.strip():
        raise ValueError("candidate_feature is required.")
    feature_names = req.payload.get("feature_names")
    if not isinstance(feature_names, list) or not all(isinstance(item, str) for item in feature_names):
        raise KeyError("Artifact payload does not include valid 'feature_names'.")
    normalized_comparisons: list[str] = []
    seen: set[str] = set()
    for feature in req.comparison_features:
        stripped = str(feature).strip()
        if not stripped or stripped == req.candidate_feature or stripped in seen:
            continue
        normalized_comparisons.append(stripped)
        seen.add(stripped)
    if req.candidate_feature not in feature_names:
        raise ValueError(f"candidate_feature not found in artifact features: {req.candidate_feature}")
    # Standalone validation scenarios may intentionally exclude overlap features.
    return [feature for feature in normalized_comparisons if feature in feature_names]


def _ensure_held_year(df_train: pd.DataFrame) -> pd.DataFrame:
    df_train_with_year = df_train.copy()
    if "held_year" not in df_train_with_year.columns:
        held_dt = pd.to_datetime(df_train_with_year["held_date"], errors="coerce")
        if held_dt.isna().any():
            raise ValueError("held_date conversion failed while building held_year.")
        df_train_with_year["held_year"] = held_dt.dt.year.astype(int)
    else:
        df_train_with_year["held_year"] = pd.to_numeric(
            df_train_with_year["held_year"],
            errors="raise",
        ).astype(int)
    return df_train_with_year


def _sample_frame(
    *,
    feature_frame: pd.DataFrame,
    target: pd.Series | None,
    sample_size_cap: int,
    random_state: int,
) -> tuple[pd.DataFrame, pd.Series | None]:
    if len(feature_frame) <= sample_size_cap:
        return feature_frame.copy(), None if target is None else target.copy()
    sampled_frame = feature_frame.sample(n=sample_size_cap, random_state=random_state)
    sampled_target = None if target is None else target.loc[sampled_frame.index].copy()
    return sampled_frame.copy(), sampled_target


def _concat_sampled_year_frames(
    *,
    split_frames: dict[str, tuple[pd.DataFrame, pd.Series]],
    df_train: pd.DataFrame,
    sample_size_cap: int,
    random_state: int,
) -> pd.DataFrame:
    sampled_parts: list[pd.DataFrame] = []
    for feature_frame, _ in split_frames.values():
        sampled_frame, _ = _sample_frame(
            feature_frame=feature_frame,
            target=None,
            sample_size_cap=sample_size_cap,
            random_state=random_state,
        )
        if sampled_frame.empty:
            continue
        sampled_part = sampled_frame.copy()
        sampled_part["held_year"] = pd.to_numeric(df_train.loc[sampled_part.index, "held_year"], errors="raise").astype(int)
        sampled_parts.append(sampled_part)
    if not sampled_parts:
        return pd.DataFrame(columns=["held_year"])
    return pd.concat(sampled_parts, axis=0)


def _resolve_base_model(payload: dict[str, Any]) -> Any:
    model = payload.get("model")
    if model is None:
        raise KeyError("Artifact payload does not include 'model'.")
    return model
