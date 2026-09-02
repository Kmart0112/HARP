from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from harp.core.training import BinaryDataset, build_binary_dataset
from harp.interface.ports import (
    ArtifactStorePort,
    FeatureDefinitionPort,
    ManifestStorePort,
    TrainingRepositoryPort,
)


@dataclass(frozen=True)
class TrainFlowResult:
    train_rows: int
    val_rows: int
    test_rows: int
    artifact_out: str
    manifest_out: str
    legacy_artifact_out: str | None
    metrics: dict[str, float | None]
    calibration_info: dict[str, Any] | None = None
    tracking_run_id: str | None = None


def load_feature_set_from_contract(
    *,
    feature_definition_port: FeatureDefinitionPort,
    contract_path: str,
    feature_set_name: str,
) -> tuple[list[str], list[str]]:
    feature_set = feature_definition_port.load_feature_set(
        source_path=contract_path,
        feature_set_name=feature_set_name,
        mode="production",
    )
    return list(feature_set.feature_names), list(feature_set.cat_features)


def materialize_dataset(
    *,
    training_repository: TrainingRepositoryPort,
    feature_definition_port: FeatureDefinitionPort,
    mart_table: str,
    contract_path: str,
    feature_set_name: str,
    target_col: str,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
    limit: int | None,
    where: dict[str, object] | None = None,
) -> tuple[pd.DataFrame, BinaryDataset]:
    feature_names, cat_features = load_feature_set_from_contract(
        feature_definition_port=feature_definition_port,
        contract_path=contract_path,
        feature_set_name=feature_set_name,
    )
    max_year = max(int(train_year_end), int(test_year))
    df_train = training_repository.load_training_frame(
        max_year=max_year,
        limit=limit,
        mart_table=mart_table,
        where=where,
    )
    ds = build_binary_dataset(
        df=df_train,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col=target_col,
        train_year_start=int(train_year_start),
        train_year_end=int(train_year_end),
        test_year=int(test_year),
    )
    return df_train, ds


def persist_training_outputs(
    *,
    artifact_store_port: ArtifactStorePort,
    manifest_store_port: ManifestStorePort,
    payload: dict,
    model_type: str,
    artifact_out: str,
    manifest_out: str,
    legacy_copy: bool,
    legacy_artifact_out: str,
    feature_names: list[str],
    cat_features: list[str],
    train_year_start: int,
    train_year_end: int,
    test_year: int,
    metrics: dict[str, float | None],
    source_table: str,
    note: str,
    calibration_method: str = "none",
) -> str | None:
    artifact_store_port.save_artifact(payload, artifact_out)
    legacy_path = artifact_store_port.copy_legacy(
        src=artifact_out,
        dst=legacy_artifact_out,
        enabled=legacy_copy,
    )

    note_with_calibration = note
    if calibration_method and calibration_method != "none":
        note_with_calibration = f"{note} | calibration={calibration_method}"

    manifest = manifest_store_port.build_manifest(
        model_type=model_type,
        artifact_path=artifact_out,
        feature_names=feature_names,
        cat_features=cat_features,
        train_window={
            "train_year_start": int(train_year_start),
            "train_year_end": int(train_year_end),
            "test_year": int(test_year),
        },
        metrics=metrics,
        source_table=source_table,
        note=note_with_calibration,
    )
    manifest_store_port.validate_manifest(manifest)
    manifest_store_port.write_manifest(manifest, manifest_out)
    return legacy_path
