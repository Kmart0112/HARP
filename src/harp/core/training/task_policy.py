from __future__ import annotations

from dataclasses import dataclass

from .task_types import CalibrationMethod, ModelType, TaskKind


@dataclass(frozen=True)
class TrainingTaskSpec:
    task_kind: TaskKind
    target_col: str
    model_type: ModelType
    note: str
    requires_calibration_odds_col: bool = False


@dataclass(frozen=True)
class PredictTaskSpec:
    task_kind: TaskKind
    model_type: ModelType
    calibration_method: CalibrationMethod


TRAINING_TASK_SPECS: dict[tuple[TaskKind, CalibrationMethod], TrainingTaskSpec] = {
    (TaskKind.PLACE, CalibrationMethod.NONE): TrainingTaskSpec(
        task_kind=TaskKind.PLACE,
        target_col="is_place",
        model_type=ModelType.PLACE,
        note="track4 place model",
    ),
    (TaskKind.PLACE, CalibrationMethod.PLATT_LOGODDS): TrainingTaskSpec(
        task_kind=TaskKind.PLACE,
        target_col="is_place",
        model_type=ModelType.PLACE_PLATT,
        note="track4 place platt model",
        requires_calibration_odds_col=True,
    ),
    (TaskKind.WIN, CalibrationMethod.NONE): TrainingTaskSpec(
        task_kind=TaskKind.WIN,
        target_col="is_win",
        model_type=ModelType.WIN,
        note="track4 win model",
    ),
}

UNSUPPORTED_TRAINING_TASK_ERRORS: dict[tuple[TaskKind, CalibrationMethod], str] = {
    (TaskKind.WIN, CalibrationMethod.PLATT_LOGODDS): (
        "calibration_method=platt_logodds is not allowed for pipeline_kind=win."
    ),
}

MODEL_TYPE_ALIASES: dict[str, ModelType] = {
    "": ModelType.PLACE,
    "place": ModelType.PLACE,
    "fukusho": ModelType.PLACE,
    "place_platt": ModelType.PLACE_PLATT,
    "fukusho_platt": ModelType.PLACE_PLATT,
    "win": ModelType.WIN,
    "tansho": ModelType.WIN,
}

PREDICT_TASK_SPECS: dict[ModelType, PredictTaskSpec] = {
    ModelType.PLACE: PredictTaskSpec(
        task_kind=TaskKind.PLACE,
        model_type=ModelType.PLACE,
        calibration_method=CalibrationMethod.NONE,
    ),
    ModelType.PLACE_PLATT: PredictTaskSpec(
        task_kind=TaskKind.PLACE,
        model_type=ModelType.PLACE_PLATT,
        calibration_method=CalibrationMethod.PLATT_LOGODDS,
    ),
    ModelType.WIN: PredictTaskSpec(
        task_kind=TaskKind.WIN,
        model_type=ModelType.WIN,
        calibration_method=CalibrationMethod.NONE,
    ),
}


def _resolve_task_kind(value: TaskKind | str, *, field_name: str) -> TaskKind:
    try:
        return value if isinstance(value, TaskKind) else TaskKind.from_str(str(value))
    except ValueError as exc:
        candidates = ", ".join(kind.value for kind in TaskKind)
        raise ValueError(f"Unknown {field_name}: {value!r}. candidates={candidates}") from exc


def _resolve_calibration_method(value: CalibrationMethod | str) -> CalibrationMethod:
    try:
        return value if isinstance(value, CalibrationMethod) else CalibrationMethod.from_str(str(value))
    except ValueError as exc:
        raise ValueError(f"Unsupported calibration method: {value}") from exc


def resolve_training_task_spec(
    *,
    pipeline_kind: TaskKind | str,
    calibration_method: CalibrationMethod | str,
) -> TrainingTaskSpec:
    resolved_pipeline_kind = _resolve_task_kind(pipeline_kind, field_name="pipeline_kind")
    resolved_calibration_method = _resolve_calibration_method(calibration_method)
    key = (resolved_pipeline_kind, resolved_calibration_method)
    try:
        return TRAINING_TASK_SPECS[key]
    except KeyError as exc:
        message = UNSUPPORTED_TRAINING_TASK_ERRORS.get(
            key,
            (
                "Unsupported training task combination: "
                f"pipeline_kind={pipeline_kind!r}, calibration_method={calibration_method!r}"
            ),
        )
        raise ValueError(message) from exc


def resolve_model_type(value: ModelType | str) -> ModelType:
    if isinstance(value, ModelType):
        return value
    normalized = str(value).strip().lower()
    try:
        return MODEL_TYPE_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported model_type: {value!r}") from exc


def resolve_predict_task_spec(
    *,
    model_type: ModelType | str,
    has_calibration_payload: bool = False,
) -> PredictTaskSpec:
    try:
        resolved_model_type = resolve_model_type(model_type)
    except ValueError:
        if has_calibration_payload:
            resolved_model_type = ModelType.PLACE_PLATT
        else:
            raise

    if resolved_model_type is ModelType.PLACE and has_calibration_payload:
        resolved_model_type = ModelType.PLACE_PLATT
    return PREDICT_TASK_SPECS[resolved_model_type]


def validate_training_calibration(
    *,
    task_kind: TaskKind | str,
    calibration_method: CalibrationMethod | str,
    calibration_odds_col: str | None,
) -> None:
    spec = resolve_training_task_spec(
        pipeline_kind=task_kind,
        calibration_method=calibration_method,
    )
    has_odds_col = calibration_odds_col is not None and bool(str(calibration_odds_col).strip())

    if spec.requires_calibration_odds_col:
        if not has_odds_col:
            raise ValueError("calibration_odds_col is required for calibration_method=platt_logodds.")
        return
    if has_odds_col:
        raise ValueError("calibration_odds_col is not allowed when calibration_method=none.")
