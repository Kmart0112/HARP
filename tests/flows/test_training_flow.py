from __future__ import annotations

from unittest.mock import create_autospec

import pandas as pd

from harp.core.feature_definitions import FeatureSetDefinition
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
    repository.load_training_frame.return_value = _training_frame()

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
        mart_table="mart.train_features",
        contract_path="contracts/features",
        source_table="mart.train_features",
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
