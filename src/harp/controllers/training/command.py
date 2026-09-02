from __future__ import annotations

from dataclasses import dataclass

from harp.core.training.task_policy import resolve_training_task_spec
from harp.usecase.training.dto import CalibrationMethod, TrainPipelineKind, TrainRequest


DEFAULT_TRAINING_WHERE: dict[str, object] = {
    "race_level__neq": 0,
    "race_level__lte": 3,
}

DEFAULT_FEATURE_SET_BY_PIPELINE: dict[TrainPipelineKind, str] = {
    TrainPipelineKind.PLACE: "place_v1",
    TrainPipelineKind.WIN: "win_v1",
}


@dataclass(frozen=True)
class TrainCommand:
    """Command values for a model training run.

    Args:
        pipeline_kind: Training pipeline kind, such as place or win.
        train_year_start: First training year.
        train_year_end: Last training year.
        test_year: Holdout test year.
        artifact_out: Output path for the model artifact.
        manifest_out: Output path for the model manifest.
        legacy_copy: Whether to write the legacy artifact copy.
        legacy_artifact_out: Legacy artifact output path.
        calibration_method: Optional calibration method. Defaults to none.
        calibration_odds_col: Optional odds column used by calibration.
        feature_set_name: Optional feature set override.
        limit: Optional training row limit.
        where: Optional extra training filter map.
    """

    pipeline_kind: TrainPipelineKind
    train_year_start: int
    train_year_end: int
    test_year: int
    artifact_out: str
    manifest_out: str
    legacy_copy: bool
    legacy_artifact_out: str
    calibration_method: CalibrationMethod | None = None
    calibration_odds_col: str | None = None
    feature_set_name: str | None = None
    limit: int | None = None
    where: dict[str, object] | None = None


def resolve_training_where(where: dict[str, object] | None) -> dict[str, object]:
    """Merge caller-provided training filters with controller defaults.

    Args:
        where: Optional extra training filter map.
    """

    merged = dict(DEFAULT_TRAINING_WHERE)
    if where:
        merged.update(where)
    return merged


def _normalize_train_mode(
    pipeline_kind: TrainPipelineKind | str,
    calibration_method: CalibrationMethod | str | None,
) -> tuple[TrainPipelineKind, CalibrationMethod]:
    try:
        resolved_pipeline_kind = (
            pipeline_kind
            if isinstance(pipeline_kind, TrainPipelineKind)
            else TrainPipelineKind.from_str(str(pipeline_kind))
        )
    except ValueError as exc:
        candidates = ", ".join(kind.value for kind in TrainPipelineKind)
        raise ValueError(f"Unknown pipeline_kind: {pipeline_kind!r}. candidates={candidates}") from exc

    if calibration_method is None:
        return resolved_pipeline_kind, CalibrationMethod.NONE
    resolved_calibration_method = (
        calibration_method
        if isinstance(calibration_method, CalibrationMethod)
        else CalibrationMethod.from_str(str(calibration_method))
    )
    return resolved_pipeline_kind, resolved_calibration_method


def resolve_train_feature_set_name(
    *,
    pipeline_kind: TrainPipelineKind,
    feature_set_name: str | None,
) -> str:
    """Resolve the training feature set name for a pipeline kind.

    Args:
        pipeline_kind: Training pipeline kind.
        feature_set_name: Optional explicit feature set name.
    """

    if feature_set_name is not None and str(feature_set_name).strip():
        return str(feature_set_name).strip()
    try:
        return DEFAULT_FEATURE_SET_BY_PIPELINE[pipeline_kind]
    except KeyError as exc:
        candidates = ", ".join(kind.value for kind in DEFAULT_FEATURE_SET_BY_PIPELINE)
        raise ValueError(f"Unknown pipeline_kind: {pipeline_kind!r}. candidates={candidates}") from exc


def build_train_request(cmd: TrainCommand) -> TrainRequest:
    """Build the training usecase request from command values.

    Args:
        cmd: CLI-level command values for training.
    """

    resolved_pipeline_kind, resolved_calibration_method = _normalize_train_mode(
        pipeline_kind=cmd.pipeline_kind,
        calibration_method=cmd.calibration_method,
    )
    feature_set_name = resolve_train_feature_set_name(
        pipeline_kind=resolved_pipeline_kind,
        feature_set_name=cmd.feature_set_name,
    )
    task_spec = resolve_training_task_spec(
        pipeline_kind=resolved_pipeline_kind.value,
        calibration_method=resolved_calibration_method.value,
    )

    return TrainRequest(
        pipeline_kind=resolved_pipeline_kind,
        train_year_start=cmd.train_year_start,
        train_year_end=cmd.train_year_end,
        test_year=cmd.test_year,
        artifact_out=cmd.artifact_out,
        manifest_out=cmd.manifest_out,
        legacy_copy=cmd.legacy_copy,
        legacy_artifact_out=cmd.legacy_artifact_out,
        calibration_method=resolved_calibration_method,
        calibration_odds_col=cmd.calibration_odds_col,
        feature_set_name=feature_set_name,
        task_spec=task_spec,
        limit=cmd.limit,
        where=resolve_training_where(cmd.where),
    )
