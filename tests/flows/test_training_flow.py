from __future__ import annotations

from unittest.mock import create_autospec

import pandas as pd

from harp.core.feature_definitions import FeatureSetDefinition
from harp.core.odds import OddsPolicy, select_odds
from harp.core.race_inputs import RaceInputs
from harp.core.training.task_policy import resolve_training_task_spec
from harp.interface.ports import (
    ArtifactStorePort,
    FeatureDefinitionPort,
    FileGatewayPort,
    ManifestStorePort,
    TrackingPort,
    TrainingRepositoryPort,
)
from harp.usecase.training.dto import (
    CalibrationMethod,
    TrainDeps,
    TrainPipelineKind,
    TrainRequest,
)
from harp.usecase.training.usecase import run_train_pipeline_usecase


def _training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year, count in ((2018, 24), (2019, 8), (2020, 8)):
        for index in range(count):
            rows.append(
                {
                    "held_year": year,
                    "held_date": f"{year}-06-01",
                    "race_id": f"{year}-{index // 8}",
                    "horse_number": index % 8 + 1,
                    "scheduled_start_at": f"{year}-06-01T06:10:00+00:00",
                    "speed": float(index + (year - 2018) * 3),
                    "course": "turf" if index % 2 == 0 else "dirt",
                    "is_place": index % 2,
                    "is_win": 1 if index % 4 == 0 else 0,
                }
            )
    return pd.DataFrame(rows)


def _request() -> TrainRequest:
    task_spec = resolve_training_task_spec(
        pipeline_kind=TrainPipelineKind.PLACE,
        calibration_method=CalibrationMethod.NONE,
    )
    return TrainRequest(
        pipeline_kind=TrainPipelineKind.PLACE,
        train_year_start=2018,
        train_year_end=2019,
        test_year=2020,
        artifact_out="artifacts/place.pkl",
        manifest_out="artifacts/place.json",
        legacy_copy=False,
        legacy_artifact_out="models/place.pkl",
        feature_set_name="place_v1",
        task_spec=task_spec,
        calibration_method=CalibrationMethod.NONE,
        tracking_experiment_name="training",
        tracking_run_name="place-flow",
    )


def _deps() -> tuple[TrainDeps, ArtifactStorePort, ManifestStorePort, TrackingPort]:
    repository = create_autospec(TrainingRepositoryPort, instance=True, spec_set=True)
    frame = _training_frame()
    quotes = frame[["race_id", "horse_number"]].copy()
    quotes["win_odds"] = 4.0
    quotes["place_low"] = 1.8
    quotes["place_high"] = 2.0
    quotes["win_popularity"] = 1
    quotes["published_at"] = frame.held_year.astype(str) + "-06-01T06:00:00+00:00"
    quotes["available_at"] = None
    repository.load_training_input.return_value = RaceInputs(
        frame, select_odds(frame, quotes, OddsPolicy.pre_start(max_age_seconds=300)), "fixture-v1")

    feature_definitions = create_autospec(FeatureDefinitionPort, instance=True, spec_set=True)
    feature_definitions.load_feature_set.return_value = FeatureSetDefinition(
        name="place_v1",
        feature_names=("speed", "course"),
        cat_features=("course",),
    )

    artifact_store = create_autospec(ArtifactStorePort, instance=True, spec_set=True)
    artifact_store.copy_legacy.return_value = None

    manifest_store = create_autospec(ManifestStorePort, instance=True, spec_set=True)
    manifest_store.build_manifest.return_value = {
        "model_type": "place",
        "artifact_path": "artifacts/place.pkl",
    }

    tracking = create_autospec(TrackingPort, instance=True, spec_set=True)
    tracking.start_run.return_value = "run-1"

    file_gateway = create_autospec(FileGatewayPort, instance=True, spec_set=True)
    deps = TrainDeps(
        training_repository=repository,
        file_gateway=file_gateway,
        feature_definition_port=feature_definitions,
        artifact_store_port=artifact_store,
        manifest_store_port=manifest_store,
        contract_path="contracts/features",
        tracking_port=tracking,
    )
    return deps, artifact_store, manifest_store, tracking


def test_training_flow_materializes_model_manifest_and_tracking_result() -> None:
    deps, artifact_store, manifest_store, tracking = _deps()

    result = run_train_pipeline_usecase(_request(), deps)

    assert result.train_rows == 24
    assert result.val_rows == 8
    assert result.test_rows == 8
    assert result.artifact_out == "artifacts/place.pkl"
    assert result.manifest_out == "artifacts/place.json"
    assert result.legacy_artifact_out is None
    assert result.tracking_run_id == "run-1"
    assert set(result.metrics) == {"auc", "brier", "logloss"}

    saved_payload = artifact_store.save_artifact.call_args.args[0]
    assert saved_payload["model_type"] == "place"
    assert saved_payload["feature_names"] == ["speed", "course"]
    assert saved_payload["cat_features"] == ["course"]
    assert saved_payload["split_info"] == {
        "train_year_start": 2018,
        "train_year_end": 2019,
        "test_year": 2020,
        "n_train_rows": 24,
        "n_val_rows": 8,
        "n_test_rows": 8,
    }
    manifest_store.write_manifest.assert_called_once_with(
        manifest_store.build_manifest.return_value,
        "artifacts/place.json",
    )
    tracking.set_terminated.assert_called_once_with("run-1", status="FINISHED")


def test_training_records_odds_coverage_and_never_imputes_missing_market_prices():
    deps, artifact_store, _, _ = _deps()
    inputs = deps.training_repository.load_training_input.return_value
    quotes = inputs.odds.frame
    quotes.loc[0, "win_odds"] = None
    deps.training_repository.load_training_input.return_value = RaceInputs(
        inputs.frame, select_odds(inputs.frame, quotes, inputs.odds.policy), "with-missing")
    deps.feature_definition_port.load_feature_set.return_value = FeatureSetDefinition(
        name="odds_model", feature_names=("speed", "log_odds_tansho"), cat_features=())
    result = run_train_pipeline_usecase(_request(), deps)
    assert result.train_rows == 23
    saved = artifact_store.save_artifact.call_args.args[0]
    assert {"year": 2018, "reason": "win_unavailable", "rows": 1} in saved["training_coverage"]
    assert {"year": 2018, "reason": "included", "rows": 23} in saved["training_coverage"]
    assert sum(row["rows"] for row in saved["training_coverage"]) == 40
    assert saved["input_contract"]["feature_names"] == ["speed", "log_odds_tansho"]
    assert saved["input_contract"]["training_odds_policy"]["mode"] == "pre_start"
    assert saved["input_contract"]["allowed_prediction_policies"] == []


def test_odds_free_training_keeps_rows_without_market_quotes():
    deps, artifact_store, _, _ = _deps()
    inputs = deps.training_repository.load_training_input.return_value
    quotes = inputs.odds.frame
    quotes["win_odds"] = None
    deps.training_repository.load_training_input.return_value = RaceInputs(
        inputs.frame, select_odds(inputs.frame, quotes, inputs.odds.policy), "without-win")
    result = run_train_pipeline_usecase(_request(), deps)
    assert result.train_rows == 24
    saved = artifact_store.save_artifact.call_args.args[0]
    assert all(row["reason"] == "included" for row in saved["training_coverage"])


def test_training_artifact_contract_passes_real_manifest_validation(tmp_path):
    import json
    from dataclasses import replace

    from harp.adapters.driven.storage.manifest_store import JsonManifestStoreAdapter
    deps, _, _, _ = _deps()
    deps = replace(deps, manifest_store_port=JsonManifestStoreAdapter())
    request = replace(_request(), manifest_out=str(tmp_path / "model.json"), artifact_out="pipeline/artifacts/models/contract_test.pkl",
                      allowed_prediction_policies=("latest_before",))
    run_train_pipeline_usecase(request, deps)
    manifest = json.loads((tmp_path / "model.json").read_text())
    assert manifest["input_contract"]["allowed_prediction_policies"] == ["latest_before"]
    assert sum(row["rows"] for row in manifest["training_coverage"]) == 40


def test_platt_training_uses_selected_win_odds_and_records_exclusion():
    from dataclasses import replace
    deps, artifact_store, _, _ = _deps()
    inputs = deps.training_repository.load_training_input.return_value
    quotes = inputs.odds.frame
    quotes.loc[0, "win_odds"] = None
    deps.training_repository.load_training_input.return_value = RaceInputs(
        inputs.frame, select_odds(inputs.frame, quotes, inputs.odds.policy), "platt-missing-win")
    request = replace(_request(), calibration_method=CalibrationMethod.PLATT_LOGODDS,
                      calibration_odds_col="win_odds",
                      task_spec=resolve_training_task_spec(pipeline_kind=TrainPipelineKind.PLACE,
                                                          calibration_method=CalibrationMethod.PLATT_LOGODDS))
    result = run_train_pipeline_usecase(request, deps)
    assert result.train_rows == 23
    assert result.calibration_info["odds_field"] == "win_odds"
    assert result.calibration_info["oof_n"] == 23
    payload = artifact_store.save_artifact.call_args.args[0]
    assert payload["model_type"] == "place_platt"
    assert {"year": 2018, "reason": "win_unavailable", "rows": 1} in payload["training_coverage"]
