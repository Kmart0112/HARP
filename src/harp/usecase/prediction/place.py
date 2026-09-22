from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from harp.core.inference import (
    filter_edge_candidates,
    select_output_columns,
)
from harp.core.inference.ev_calculator import PlaceOddsMethod
from harp.core.inference.odds_prediction import evaluate_place_inputs
from harp.core.input_contract import require_model_input_contract
from harp.core.odds import OddsContractError, OddsPolicy
from harp.core.race_inputs import RaceInputQuery
from harp.core.training import CalibrationMethod, TaskKind, resolve_predict_task_spec
from harp.interface.ports import (
    FileGatewayPort,
    InferenceRepositoryPort,
    ManifestReaderPort,
    ModelLoaderPort,
)
from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort


@dataclass(frozen=True)
class PredictPlaceRequest:
    artifact_path: str
    manifest_path: str | None
    from_date: str
    to_date: str
    limit: int | None
    odds_method: PlaceOddsMethod
    edge_threshold: float
    bankroll: float
    kelly_fraction: float
    kelly_cap: float
    as_of: datetime
    max_quote_age_seconds: float
    replay_snapshot_id: str | None = None


@dataclass(frozen=True)
class PredictPlaceDeps:
    inference_repository: InferenceRepositoryPort
    model_loader_port: ModelLoaderPort
    manifest_reader_port: ManifestReaderPort
    file_gateway: FileGatewayPort
    snapshot_store: PredictionSnapshotStorePort


@dataclass(frozen=True)
class PredictPlaceResult:
    from_date: str
    to_date: str
    race_entries: pd.DataFrame
    edge_candidates: pd.DataFrame
    input_snapshot_id: str
    shifted_race_entries: pd.DataFrame | None = None
    shifted_edge_candidates: pd.DataFrame | None = None


def _resolve_model_type(
    *,
    req: PredictPlaceRequest,
    deps: PredictPlaceDeps,
    payload: dict[str, object],
) -> str:
    if req.manifest_path is not None:
        model_type = deps.manifest_reader_port.read_model_type(req.manifest_path)
        if model_type is not None:
            return model_type

    payload_model_type = payload.get("model_type")
    if isinstance(payload_model_type, str) and payload_model_type.strip():
        return payload_model_type.strip()

    return "place"


def _has_platt_payload(payload: dict[str, object]) -> bool:
    calibration = payload.get("calibration")
    if not isinstance(calibration, dict):
        return False
    method = calibration.get("method")
    return isinstance(method, str) and method.strip().lower() == CalibrationMethod.PLATT_LOGODDS.value


def _resolve_task_and_calibration(
    *,
    model_type: str,
    payload: dict[str, object],
) -> tuple[TaskKind, CalibrationMethod]:
    try:
        task_spec = resolve_predict_task_spec(
            model_type=model_type,
            has_calibration_payload=_has_platt_payload(payload),
        )
    except ValueError as exc:
        raise ValueError(f"Unsupported model_type for predict_place_usecase: {model_type!r}") from exc
    if task_spec.task_kind is not TaskKind.PLACE:
        raise ValueError(f"predict_place_usecase supports place models only, got model_type={model_type!r}")
    return task_spec.task_kind, task_spec.calibration_method



def run_predict_place_usecase(req: PredictPlaceRequest, deps: PredictPlaceDeps) -> PredictPlaceResult:
    payload = deps.model_loader_port.load_model_payload(req.artifact_path)
    model_type = _resolve_model_type(req=req, deps=deps, payload=payload)
    _task, calibration = _resolve_task_and_calibration(model_type=model_type, payload=payload)
    policy = OddsPolicy.latest(req.as_of, req.max_quote_age_seconds)
    require_model_input_contract(payload, policy)
    query = RaceInputQuery(
        from_date=req.from_date, to_date=req.to_date,
        feature_names=tuple(payload["feature_names"]), odds_policy=policy,
        max_races=req.limit,
        categorical_features=tuple(payload.get("cat_features", ())),
        filters={"horse_number__gt": 0},
    )
    metadata = {
        "model_sha256": payload["artifact_sha256"], "model_type": model_type,
        "feature_names": list(query.feature_names), "from_date": req.from_date, "to_date": req.to_date,
        "policy": policy.to_dict(),
        "max_races": req.limit, "odds_method": req.odds_method.value,
        "edge_threshold": req.edge_threshold, "bankroll": req.bankroll,
        "kelly_fraction": req.kelly_fraction, "kelly_cap": req.kelly_cap,
    }
    if req.replay_snapshot_id:
        stored = deps.snapshot_store.load(req.replay_snapshot_id)
        if stored.metadata != metadata:
            raise OddsContractError("replay model or input request differs from saved snapshot")
        inputs = stored.inputs
    else:
        inputs = deps.inference_repository.load_prediction_input(query)
    inputs.validate_query(query)
    evaluated = evaluate_place_inputs(
        inputs, payload, use_platt=calibration is CalibrationMethod.PLATT_LOGODDS,
        method=req.odds_method, bankroll=req.bankroll,
        kelly_fraction=req.kelly_fraction, kelly_cap=req.kelly_cap,
    )

    def candidates(frame):
        eligible = frame.loc[frame.ev_status.eq("calculated")]
        return select_output_columns(filter_edge_candidates(
            eligible, threshold=req.edge_threshold, edge_col="edge",
            race_id_col="race_id", rank_col="edge", rank_desc=True))

    snapshot_id = req.replay_snapshot_id or deps.snapshot_store.save(inputs, metadata)
    return PredictPlaceResult(
        from_date=req.from_date, to_date=req.to_date,
        race_entries=select_output_columns(evaluated.rows),
        edge_candidates=candidates(evaluated.rows),
        input_snapshot_id=snapshot_id,
        shifted_race_entries=(select_output_columns(evaluated.shifted_rows)
                              if evaluated.shifted_rows is not None else None),
        shifted_edge_candidates=(candidates(evaluated.shifted_rows)
                                 if evaluated.shifted_rows is not None else None),
    )
