from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ShapMetricsContext:
    delta_auc: float
    delta_logloss: float
    delta_brier: float | None
    metrics_run_label: str
    validation_mode: str


@dataclass(frozen=True)
class CandidateShapSummary:
    feature: str
    global_rank: int
    mean_abs_shap: float
    importance_share: float
    top_n_hit: bool
    sample_rows: int
    split: str
    held_year_min: int
    held_year_max: int
    interaction_feature: str | None
    outlier_share_top1pct: float


@dataclass(frozen=True)
class ShapReviewVerdict:
    metrics_judgement: str
    shap_judgement: str
    final_recommendation: str
    review_notes: tuple[str, ...]


@dataclass(frozen=True)
class ShapReviewPackage:
    explanation: Any
    feature_frame: pd.DataFrame
    y_true: pd.Series
    pred_proba: pd.Series
    pred_label: pd.Series
    candidate_feature: str
    comparison_features: tuple[str, ...]
    interaction_feature: str | None


@dataclass(frozen=True)
class CandidateShapReviewBundle:
    metrics_context: ShapMetricsContext
    candidate_summary: CandidateShapSummary
    comparison_summary: pd.DataFrame
    split_stability_summary: pd.DataFrame
    year_stability_summary: pd.DataFrame
    local_case_summary: pd.DataFrame
    local_case_indices: dict[str, list[int]]
    verdict: ShapReviewVerdict
    shap_package: ShapReviewPackage


def build_tree_shap_explanation(model: Any, feature_frame: pd.DataFrame) -> Any:
    import shap

    explainer = shap.TreeExplainer(model)
    raw = explainer(feature_frame)
    if hasattr(shap, "Explanation") and isinstance(raw, shap.Explanation):
        explanation = raw
    else:
        raw_values = explainer.shap_values(feature_frame)
        if isinstance(raw_values, list):
            values = raw_values[1]
        else:
            values = raw_values
        if hasattr(values, "values"):
            values = values.values
        values = np.asarray(values)
        if values.ndim == 2 and values.shape[1] == feature_frame.shape[1] + 1:
            values = values[:, :-1]
        base_value = explainer.expected_value
        if isinstance(base_value, list):
            base_value = base_value[1]
        base_values = np.repeat(float(base_value), repeats=len(feature_frame))
        explanation = shap.Explanation(
            values=values,
            base_values=base_values,
            data=feature_frame,
            feature_names=list(feature_frame.columns),
        )
    if np.asarray(explanation.values).ndim != 2:
        raise ValueError("SHAP explanation must be 2-dimensional for tabular review.")
    return explanation


def resolve_interaction_feature(
    explanation: Any,
    candidate_feature: str,
    comparison_features: list[str] | tuple[str, ...],
) -> str | None:
    feature_names = list(getattr(explanation, "feature_names", []) or [])
    if candidate_feature not in feature_names:
        raise ValueError(f"candidate_feature not found in explanation: {candidate_feature}")
    for feature in comparison_features:
        if feature and feature != candidate_feature and feature in feature_names:
            return feature

    feature_frame = _explanation_to_frame(explanation)
    candidate_values = pd.to_numeric(feature_frame[candidate_feature], errors="coerce")
    if candidate_values.notna().sum() < 2:
        return None

    best_feature: str | None = None
    best_score = -np.inf
    for feature in feature_frame.columns:
        if feature == candidate_feature:
            continue
        comp_values = pd.to_numeric(feature_frame[feature], errors="coerce")
        valid = candidate_values.notna() & comp_values.notna()
        if int(valid.sum()) < 2:
            continue
        score = abs(float(np.corrcoef(candidate_values[valid], comp_values[valid])[0, 1]))
        if np.isnan(score):
            continue
        if score > best_score:
            best_score = score
            best_feature = feature
    return best_feature


def build_candidate_shap_review(
    *,
    explanation: Any,
    feature_frame: pd.DataFrame,
    y_true: pd.Series,
    pred_proba: pd.Series,
    candidate_feature: str,
    comparison_features: list[str],
    metrics_context: ShapMetricsContext,
    split_name: str,
    held_year_min: int,
    held_year_max: int,
    split_explanations: dict[str, tuple[Any, pd.DataFrame]],
    year_explanations: dict[int, tuple[Any, pd.DataFrame]],
    interaction_feature: str | None,
    local_case_limit: int = 2,
) -> CandidateShapReviewBundle:
    feature_names = list(feature_frame.columns)
    missing = [feature for feature in [candidate_feature, *comparison_features] if feature not in feature_names]
    if missing:
        raise ValueError(f"Missing review features in sampled frame: {missing}")
    if len(feature_frame) == 0:
        raise ValueError("feature_frame must not be empty.")

    shap_matrix = _explanation_values_frame(explanation)
    mean_abs = shap_matrix.abs().mean(axis=0).sort_values(ascending=False)
    candidate_rank = int(mean_abs.index.get_loc(candidate_feature)) + 1
    candidate_mean_abs = float(mean_abs[candidate_feature])
    total_importance = float(mean_abs.sum())
    candidate_abs = shap_matrix[candidate_feature].abs().sort_values(ascending=False)
    top1pct = max(int(np.ceil(len(candidate_abs) * 0.01)), 1)
    outlier_share = float(candidate_abs.head(top1pct).sum() / candidate_abs.sum()) if float(candidate_abs.sum()) > 0 else 0.0
    importance_share = float(candidate_mean_abs / total_importance) if total_importance > 0 else 0.0

    pred_label = (pred_proba >= 0.5).astype(int)
    candidate_summary = CandidateShapSummary(
        feature=candidate_feature,
        global_rank=candidate_rank,
        mean_abs_shap=candidate_mean_abs,
        importance_share=importance_share,
        top_n_hit=bool(candidate_rank <= min(30, len(mean_abs))),
        sample_rows=int(len(feature_frame)),
        split=str(split_name),
        held_year_min=int(held_year_min),
        held_year_max=int(held_year_max),
        interaction_feature=interaction_feature,
        outlier_share_top1pct=outlier_share,
    )

    comparison_summary = _build_comparison_summary(
        shap_matrix=shap_matrix,
        feature_frame=feature_frame,
        mean_abs=mean_abs,
        candidate_feature=candidate_feature,
        comparison_features=comparison_features,
    )
    split_stability_summary = _build_stability_summary(split_explanations, candidate_feature, scope_label="split")
    year_stability_summary = _build_stability_summary(year_explanations, candidate_feature, scope_label="held_year")
    local_case_summary, local_case_indices = _build_local_case_summary(
        shap_matrix=shap_matrix,
        feature_frame=feature_frame,
        y_true=y_true,
        pred_proba=pred_proba,
        pred_label=pred_label,
        candidate_feature=candidate_feature,
        local_case_limit=local_case_limit,
    )
    verdict = _build_review_verdict(
        metrics_context=metrics_context,
        candidate_summary=candidate_summary,
        comparison_summary=comparison_summary,
        split_stability_summary=split_stability_summary,
        year_stability_summary=year_stability_summary,
        local_case_summary=local_case_summary,
    )
    shap_package = ShapReviewPackage(
        explanation=explanation,
        feature_frame=feature_frame.copy(),
        y_true=y_true.copy(),
        pred_proba=pred_proba.copy(),
        pred_label=pred_label.copy(),
        candidate_feature=candidate_feature,
        comparison_features=tuple(comparison_features),
        interaction_feature=interaction_feature,
    )
    return CandidateShapReviewBundle(
        metrics_context=metrics_context,
        candidate_summary=candidate_summary,
        comparison_summary=comparison_summary,
        split_stability_summary=split_stability_summary,
        year_stability_summary=year_stability_summary,
        local_case_summary=local_case_summary,
        local_case_indices=local_case_indices,
        verdict=verdict,
        shap_package=shap_package,
    )


def _build_comparison_summary(
    *,
    shap_matrix: pd.DataFrame,
    feature_frame: pd.DataFrame,
    mean_abs: pd.Series,
    candidate_feature: str,
    comparison_features: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    candidate_series = shap_matrix[candidate_feature]
    candidate_importance = float(mean_abs[candidate_feature])

    for feature in comparison_features:
        comparison_series = shap_matrix[feature]
        shap_corr = _safe_corr(candidate_series, comparison_series)
        value_corr = _safe_corr(
            pd.to_numeric(feature_frame[candidate_feature], errors="coerce"),
            pd.to_numeric(feature_frame[feature], errors="coerce"),
        )
        feature_importance = float(mean_abs[feature])
        redundancy_flag = "low"
        if abs(shap_corr) >= 0.9:
            redundancy_flag = "high"
        elif abs(shap_corr) >= 0.75:
            redundancy_flag = "medium"

        rows.append(
            {
                "feature": feature,
                "mean_abs_shap": feature_importance,
                "global_rank": int(mean_abs.index.get_loc(feature)) + 1,
                "candidate_minus_feature": float(candidate_importance - feature_importance),
                "candidate_to_feature_ratio": float(candidate_importance / feature_importance) if feature_importance > 0 else np.nan,
                "candidate_shap_corr": shap_corr,
                "feature_value_corr": value_corr,
                "redundancy_flag": redundancy_flag,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "feature",
                "mean_abs_shap",
                "global_rank",
                "candidate_minus_feature",
                "candidate_to_feature_ratio",
                "candidate_shap_corr",
                "feature_value_corr",
                "redundancy_flag",
            ]
        )
    return pd.DataFrame(rows).sort_values(["redundancy_flag", "mean_abs_shap"], ascending=[True, False]).reset_index(drop=True)


def _build_stability_summary(
    explanation_map: dict[Any, tuple[Any, pd.DataFrame]],
    candidate_feature: str,
    *,
    scope_label: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scope_value, (explanation, feature_frame) in explanation_map.items():
        if len(feature_frame) == 0 or candidate_feature not in feature_frame.columns:
            continue
        mean_abs = _explanation_values_frame(explanation).abs().mean(axis=0).sort_values(ascending=False)
        rows.append(
            {
                scope_label: scope_value,
                "rows": int(len(feature_frame)),
                "candidate_mean_abs_shap": float(mean_abs[candidate_feature]),
                "candidate_rank": int(mean_abs.index.get_loc(candidate_feature)) + 1,
            }
        )
    if not rows:
        return pd.DataFrame(columns=[scope_label, "rows", "candidate_mean_abs_shap", "candidate_rank"])
    return pd.DataFrame(rows).sort_values(scope_label).reset_index(drop=True)


def _build_local_case_summary(
    *,
    shap_matrix: pd.DataFrame,
    feature_frame: pd.DataFrame,
    y_true: pd.Series,
    pred_proba: pd.Series,
    pred_label: pd.Series,
    candidate_feature: str,
    local_case_limit: int,
) -> tuple[pd.DataFrame, dict[str, list[int]]]:
    case_defs = {
        "good_positive": (y_true == 1) & (pred_label == 1),
        "good_negative": (y_true == 0) & (pred_label == 0),
        "bad_positive": (y_true == 0) & (pred_label == 1),
        "bad_negative": (y_true == 1) & (pred_label == 0),
    }
    rows: list[dict[str, object]] = []
    case_indices: dict[str, list[int]] = {}
    for case_name, mask in case_defs.items():
        case_frame = pd.DataFrame(
            {
                "row_index": feature_frame.index,
                "pred_proba": pred_proba.to_numpy(),
                "candidate_feature_value": feature_frame[candidate_feature].to_numpy(),
                "candidate_shap": shap_matrix[candidate_feature].to_numpy(),
            }
        )
        filtered = case_frame.loc[mask.to_numpy()].copy()
        ascending = case_name in {"good_negative", "bad_negative"}
        filtered = filtered.sort_values("pred_proba", ascending=ascending)
        representative = filtered.head(local_case_limit)
        indices = [int(idx) for idx in representative["row_index"].tolist()]
        case_indices[case_name] = indices
        rows.append(
            {
                "case_name": case_name,
                "available_rows": int(mask.sum()),
                "representative_rows": int(len(representative)),
                "top_row_indices": ",".join(str(idx) for idx in indices),
                "mean_candidate_shap": float(filtered["candidate_shap"].mean()) if not filtered.empty else np.nan,
            }
        )
    return pd.DataFrame(rows), case_indices


def _build_review_verdict(
    *,
    metrics_context: ShapMetricsContext,
    candidate_summary: CandidateShapSummary,
    comparison_summary: pd.DataFrame,
    split_stability_summary: pd.DataFrame,
    year_stability_summary: pd.DataFrame,
    local_case_summary: pd.DataFrame,
) -> ShapReviewVerdict:
    metrics_judgement = _judge_metrics(metrics_context)
    notes: list[str] = []
    weak_effect = candidate_summary.mean_abs_shap <= 1e-6
    unstable = _has_instability(split_stability_summary) or _has_instability(year_stability_summary)
    redundant = not comparison_summary.empty and comparison_summary["redundancy_flag"].eq("high").any()
    leakage_suspicion = candidate_summary.importance_share >= 0.35 or candidate_summary.outlier_share_top1pct >= 0.60

    if weak_effect:
        notes.append("候補特徴の mean_abs_shap が極小で、全体への寄与は弱い。")
    if redundant:
        notes.append("比較特徴と SHAP 寄与が近く、冗長の疑いがある。")
    if unstable:
        notes.append("split または年度ごとに寄与順位がぶれやすく、不安定。")
    if leakage_suspicion:
        notes.append("寄与集中が強く、リークまたは外れ値依存の疑いがある。")

    local_case_available = int(local_case_summary["representative_rows"].sum()) > 0
    if metrics_judgement == "not_improved" and not notes:
        if local_case_available and candidate_summary.global_rank <= 15:
            notes.append("局所的には効いているが、metrics 全体改善にはつながっていない。")
        else:
            notes.append("SHAP 上も強い採用根拠は乏しく、metrics 未改善を補強する所見。")

    if leakage_suspicion:
        shap_judgement = "リーク懸念あり"
    elif weak_effect or redundant or unstable:
        shap_judgement = "注意"
    else:
        shap_judgement = "問題なし"

    if metrics_judgement == "improved":
        final_recommendation = "保留候補" if shap_judgement == "リーク懸念あり" else "採用候補"
    elif metrics_judgement == "mixed":
        final_recommendation = "保留候補"
    else:
        final_recommendation = "不採用候補"

    if not notes:
        notes.append("候補特徴の寄与は概ね自然で、大きな懸念は見当たらない。")
    return ShapReviewVerdict(
        metrics_judgement=metrics_judgement,
        shap_judgement=shap_judgement,
        final_recommendation=final_recommendation,
        review_notes=tuple(notes),
    )


def _judge_metrics(metrics_context: ShapMetricsContext) -> str:
    auc_improved = float(metrics_context.delta_auc) > 0
    logloss_improved = float(metrics_context.delta_logloss) < 0
    if auc_improved and logloss_improved:
        return "improved"
    if not auc_improved and not logloss_improved:
        return "not_improved"
    return "mixed"


def _has_instability(summary_df: pd.DataFrame) -> bool:
    if summary_df.empty or len(summary_df) < 2:
        return False
    series = pd.to_numeric(summary_df["candidate_mean_abs_shap"], errors="coerce").dropna()
    if len(series) < 2:
        return False
    mean_value = float(series.mean())
    if mean_value <= 0:
        return False
    cv = float(series.std(ddof=0) / mean_value)
    rank_range = float(summary_df["candidate_rank"].max() - summary_df["candidate_rank"].min())
    return cv >= 0.5 or rank_range >= 10


def _explanation_values_frame(explanation: Any) -> pd.DataFrame:
    values = np.asarray(explanation.values)
    feature_names = list(getattr(explanation, "feature_names", []) or [])
    if not feature_names:
        raise ValueError("SHAP explanation does not include feature_names.")
    if values.ndim != 2 or values.shape[1] != len(feature_names):
        raise ValueError("SHAP explanation shape does not match feature_names.")
    return pd.DataFrame(values, columns=feature_names)


def _explanation_to_frame(explanation: Any) -> pd.DataFrame:
    data = getattr(explanation, "data", None)
    feature_names = list(getattr(explanation, "feature_names", []) or [])
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if data is None:
        raise ValueError("SHAP explanation does not include source data.")
    return pd.DataFrame(data, columns=feature_names)


def _safe_corr(left: pd.Series, right: pd.Series) -> float:
    valid = left.notna() & right.notna()
    if int(valid.sum()) < 2:
        return np.nan
    if left[valid].nunique(dropna=True) < 2 or right[valid].nunique(dropna=True) < 2:
        return np.nan
    return float(left[valid].corr(right[valid]))
