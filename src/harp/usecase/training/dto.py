from __future__ import annotations

from dataclasses import dataclass

from harp.core.training.task_policy import (
    TrainingTaskSpec,
    validate_training_calibration,
)
from harp.core.training.task_types import CalibrationMethod, TaskKind
from harp.interface.ports import (
    ArtifactStorePort,
    FeatureDefinitionPort,
    FileGatewayPort,
    ManifestStorePort,
    TrackingPort,
    TrainingRepositoryPort,
)

TrainPipelineKind = TaskKind


@dataclass(frozen=True)
class TrainRequest:
    pipeline_kind: TrainPipelineKind
    train_year_start: int
    train_year_end: int
    test_year: int
    artifact_out: str
    manifest_out: str
    legacy_copy: bool
    legacy_artifact_out: str
    feature_set_name: str
    task_spec: TrainingTaskSpec
    limit: int | None = None
    where: dict[str, object] | None = None
    calibration_method: CalibrationMethod = CalibrationMethod.NONE
    calibration_odds_col: str | None = None
    tracking_experiment_name: str | None = None
    tracking_run_name: str | None = None

    def __post_init__(self) -> None:
        pipeline_kind = (
            self.pipeline_kind
            if isinstance(self.pipeline_kind, TrainPipelineKind)
            else TrainPipelineKind.from_str(str(self.pipeline_kind))
        )
        calibration_method = (
            self.calibration_method.value
            if isinstance(self.calibration_method, CalibrationMethod)
            else CalibrationMethod.from_str(str(self.calibration_method)).value
        )
        object.__setattr__(self, "pipeline_kind", pipeline_kind)
        object.__setattr__(self, "calibration_method", CalibrationMethod(calibration_method))
        validate_training_calibration(
            task_kind=self.task_spec.task_kind,
            calibration_method=calibration_method,
            calibration_odds_col=self.calibration_odds_col,
        )


@dataclass(frozen=True)
class TrainDeps:
    training_repository: TrainingRepositoryPort
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort
    artifact_store_port: ArtifactStorePort
    manifest_store_port: ManifestStorePort
    mart_table: str
    contract_path: str
    source_table: str
    tracking_port: TrackingPort | None = None
