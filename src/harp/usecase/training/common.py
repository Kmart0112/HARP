from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from harp.core.input_contract import ODDS_FEATURE_VERSION
from harp.core.odds import (
    ODDS_CONTRACT_VERSION,
    OddsPolicy,
    assemble_odds_features,
    odds_features_available,
)
from harp.core.race_inputs import RaceInputQuery
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
    contract_path: str,
    feature_set_name: str,
    target_col: str,
    train_year_start: int,
    train_year_end: int,
    test_year: int,
    limit: int | None,
    where: dict[str, object] | None = None,
    calibration_requires_odds: bool = False,
    max_quote_age_seconds: float = 300.0,
    allowed_prediction_policies: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, BinaryDataset]:
    feature_names, cat_features = load_feature_set_from_contract(
        feature_definition_port=feature_definition_port,
        contract_path=contract_path,
        feature_set_name=feature_set_name,
    )
    max_year = max(int(train_year_end), int(test_year))
    query = RaceInputQuery(
        from_date=f"{train_year_start}-01-01", to_date=f"{max_year}-12-31",
        feature_names=tuple(feature_names), target_names=(target_col,),
        odds_policy=OddsPolicy.pre_start(max_age_seconds=max_quote_age_seconds),
        max_races=limit, filters=where or {},
        categorical_features=tuple(cat_features),
    )
    inputs = training_repository.load_training_input(query)
    inputs.validate_query(query)
    frame = assemble_odds_features(inputs.frame, inputs.odds)
    quotes = inputs.odds.align(frame)
    available = odds_features_available(frame, feature_names)
    if calibration_requires_odds:
        available &= quotes.win_status.eq("available")
    target_present = frame[target_col].notna()
    included = available & target_present
    reasons = pd.Series("included", index=frame.index)
    reasons.loc[~available] = "win_" + quotes.loc[~available, "win_status"]
    reasons.loc[~available & quotes.win_status.eq("available")] = "odds_feature_unavailable"
    reasons.loc[~target_present] = "missing_target"
    coverage = (pd.DataFrame({"year": frame.held_year, "reason": reasons})
                .groupby(["year", "reason"]).size().rename("rows").reset_index().to_dict("records"))
    frame["calibration_win_odds"] = quotes.win_odds.to_numpy()
    df_train = frame.loc[included].copy().reset_index(drop=True)
    df_train.attrs["input_contract"] = {
        "odds_contract_version": ODDS_CONTRACT_VERSION,
        "odds_feature_version": ODDS_FEATURE_VERSION, "feature_names": feature_names,
        "training_odds_policy": inputs.odds.policy.to_dict(),
        "training_filters": dict(query.filters),
        "availability_basis": inputs.odds.availability_basis,
        "allowed_prediction_policies": list(allowed_prediction_policies),
        "source_revision": inputs.source_revision,
    }
    df_train.attrs["coverage"] = coverage
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
    input_contract: dict | None = None,
    training_coverage: list[dict] | None = None,
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
        input_contract=input_contract,
        training_coverage=training_coverage,
    )
    manifest_store_port.validate_manifest(manifest)
    manifest_store_port.write_manifest(manifest, manifest_out)
    return legacy_path
