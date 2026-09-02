from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from harp.core.training import BinaryDataset, build_binary_dataset
from harp.interface.ports import TrainingRepositoryPort


DEFAULT_EXPLANATION_WHERE: dict[str, object] = {
    "race_level__gte": 1,
    "race_level__lte": 3,
}


@dataclass(frozen=True)
class ArtifactExplanationDatasetRequest:
    payload: dict[str, Any]
    target_col: str
    limit: int | None = None
    where: dict[str, object] | None = None
    df_train: pd.DataFrame | None = None


@dataclass(frozen=True)
class ArtifactExplanationDatasetDeps:
    training_repository: TrainingRepositoryPort
    mart_table: str


@dataclass(frozen=True)
class ArtifactExplanationDatasetResult:
    df_train: pd.DataFrame
    ds: BinaryDataset


def _require_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise KeyError(f"Artifact payload does not include valid '{key}'.")
    return list(value)


def _require_split_info(payload: dict[str, Any]) -> tuple[int, int, int]:
    split_info = payload.get("split_info")
    if not isinstance(split_info, dict):
        raise KeyError("Artifact payload does not include valid 'split_info'.")

    required_keys = ("train_year_start", "train_year_end", "test_year")
    values: list[int] = []
    for key in required_keys:
        raw_value = split_info.get(key)
        if not isinstance(raw_value, int):
            raise KeyError(f"Artifact payload split_info is missing valid '{key}'.")
        values.append(int(raw_value))
    return values[0], values[1], values[2]


def run_rebuild_artifact_explanation_dataset_usecase(
    req: ArtifactExplanationDatasetRequest,
    deps: ArtifactExplanationDatasetDeps,
) -> ArtifactExplanationDatasetResult:
    feature_names = _require_string_list(req.payload, "feature_names")
    cat_features = _require_string_list(req.payload, "cat_features")
    train_year_start, train_year_end, test_year = _require_split_info(req.payload)

    df_train = req.df_train
    if df_train is None:
        merged_where = dict(DEFAULT_EXPLANATION_WHERE)
        if req.where:
            merged_where.update(req.where)
        df_train = deps.training_repository.load_training_frame(
            max_year=max(int(train_year_end), int(test_year)),
            limit=req.limit,
            mart_table=deps.mart_table,
            where=merged_where,
        )

    ds = build_binary_dataset(
        df=df_train,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col=req.target_col,
        train_year_start=int(train_year_start),
        train_year_end=int(train_year_end),
        test_year=int(test_year),
    )
    return ArtifactExplanationDatasetResult(df_train=df_train, ds=ds)
