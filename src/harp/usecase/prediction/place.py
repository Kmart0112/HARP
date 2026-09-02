from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from harp.core.inference import (
    FukushoType,
    ensure_merge_keys,
    filter_edge_candidates,
    join_odds_and_compute_ev,
    make_prediction_frame,
    select_output_columns,
)
from harp.core.inference.place_predictor import predict_proba_from_payload
from harp.core.training import (
    CalibrationMethod,
    TaskKind,
    apply_logit_shift_grouped,
    resolve_predict_task_spec,
)
from harp.core.training.algorithms.calibration import apply_platt_logodds
from harp.interface.ports import (
    FileGatewayPort,
    InferenceRepositoryPort,
    ManifestReaderPort,
    ModelLoaderPort,
)


@dataclass(frozen=True)
class PredictPlaceRequest:
    artifact_path: str
    manifest_path: str | None
    from_date: str
    to_date: str
    limit: int | None
    fukusho_type: FukushoType
    edge_threshold: float
    bankroll: float
    kelly_fraction: float
    kelly_cap: float


@dataclass(frozen=True)
class PredictPlaceDeps:
    inference_repository: InferenceRepositoryPort
    model_loader_port: ModelLoaderPort
    manifest_reader_port: ManifestReaderPort
    file_gateway: FileGatewayPort
    mart_table: str


@dataclass(frozen=True)
class PredictPlaceResult:
    from_date: str
    to_date: str
    race_entries: pd.DataFrame
    edge_candidates: pd.DataFrame
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


def _validate_predict_task(
    *,
    task_kind: TaskKind | str,
    calibration_method: CalibrationMethod | str,
) -> None:
    resolved_task_kind = task_kind if isinstance(task_kind, TaskKind) else TaskKind.from_str(str(task_kind))
    resolved_calibration = (
        calibration_method
        if isinstance(calibration_method, CalibrationMethod)
        else CalibrationMethod.from_str(str(calibration_method))
    )
    if resolved_task_kind is not TaskKind.PLACE:
        raise ValueError(f"predict_place_usecase supports place task only, got task_kind={task_kind!r}")
    if resolved_calibration not in PREDICT_PLACE_CALIBRATION_METHODS:
        raise ValueError(f"Unsupported calibration_method for predict_place_usecase: {calibration_method!r}")


def _identity_calibration(
    *,
    base_proba: np.ndarray,
    payload: dict[str, object],
    df_feat: pd.DataFrame,
) -> np.ndarray:
    return np.asarray(base_proba, dtype=float)


def _platt_calibration(
    *,
    base_proba: np.ndarray,
    payload: dict[str, object],
    df_feat: pd.DataFrame,
) -> np.ndarray:
    return apply_platt_logodds(
        np.asarray(base_proba, dtype=float),
        payload=payload,
        df_feat=df_feat,
        odds_col=None,
    )


CalibrationApplier = Callable[..., np.ndarray]

PREDICT_PLACE_CALIBRATION_METHODS = {
    CalibrationMethod.NONE,
    CalibrationMethod.PLATT_LOGODDS,
}

CALIBRATION_APPLIERS: dict[CalibrationMethod, CalibrationApplier] = {
    CalibrationMethod.NONE: _identity_calibration,
    CalibrationMethod.PLATT_LOGODDS: _platt_calibration,
}


def _apply_calibration(
    *,
    base_proba: np.ndarray,
    calibration_method: CalibrationMethod | str,
    payload: dict[str, object],
    df_feat: pd.DataFrame,
) -> np.ndarray:
    resolved_calibration = (
        calibration_method
        if isinstance(calibration_method, CalibrationMethod)
        else CalibrationMethod.from_str(str(calibration_method))
    )
    try:
        applier = CALIBRATION_APPLIERS[resolved_calibration]
    except KeyError as exc:
        raise ValueError(f"Unsupported calibration_method for predict_place_usecase: {calibration_method!r}") from exc
    return applier(
        base_proba=base_proba,
        payload=payload,
        df_feat=df_feat,
    )


def _apply_place_logit_shift(df_feat: pd.DataFrame, p_place: np.ndarray) -> np.ndarray:
    if "race_id" not in df_feat.columns:
        raise KeyError("df_feat must include 'race_id' for logit shift.")
    if len(df_feat) != len(p_place):
        raise ValueError("df_feat and p_place must have the same length.")

    race_ids = df_feat["race_id"].astype(str)
    horse_count = race_ids.groupby(race_ids, dropna=False).transform("size").astype(int)
    k_rule = np.where(horse_count.to_numpy(dtype=int) <= 7, 2.0, 3.0).astype(float)
    k_rule = np.minimum(k_rule, horse_count.to_numpy(dtype=float))
    k_by_group = (
        pd.DataFrame({"race_id": race_ids.to_numpy(dtype=object), "k_rule": k_rule})
        .groupby("race_id", dropna=False)["k_rule"]
        .first()
        .astype(float)
        .to_dict()
    )
    shifted = apply_logit_shift_grouped(
        np.asarray(p_place, dtype=float),
        race_ids.to_numpy(dtype=object),
        k_by_group=k_by_group,
    )
    return np.asarray(shifted, dtype=float)


def _build_output_frames(
    *,
    df_feat: pd.DataFrame,
    probability: np.ndarray,
    df_odds: pd.DataFrame,
    df_race_info: pd.DataFrame,
    req: PredictPlaceRequest,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_pred = make_prediction_frame(df_feat, probability, probability_col="p_place")
    df_ev = join_odds_and_compute_ev(
        df_pred=df_pred,
        df_odds=df_odds,
        probability_col="p_place",
        fukusho_type=req.fukusho_type,
        bankroll=req.bankroll,
        kelly_fraction=req.kelly_fraction,
        kelly_cap=req.kelly_cap,
    )

    df_ev_keyed = ensure_merge_keys(df_ev, name="ev")
    df_info_keyed = ensure_merge_keys(df_race_info, name="race_info")
    df_joined = df_ev_keyed.merge(
        df_info_keyed,
        on=["race_id", "horse_number"],
        how="left",
        suffixes=("", "_race_info"),
    )

    race_entries = select_output_columns(df_joined)
    edge_df = filter_edge_candidates(
        df_joined,
        threshold=float(req.edge_threshold),
        edge_col="edge",
        race_id_col="race_id",
        rank_col="edge",
        rank_desc=True,
    )
    edge_candidates = select_output_columns(edge_df)
    return race_entries, edge_candidates


def run_predict_place_usecase(req: PredictPlaceRequest, deps: PredictPlaceDeps) -> PredictPlaceResult:
    from_date, to_date = req.from_date, req.to_date

    df_feat = deps.inference_repository.load_recent_features(
        from_date=from_date,
        to_date=to_date,
        limit=req.limit,
        mart_table=deps.mart_table,
    )

    payload = deps.model_loader_port.load_model_payload(req.artifact_path)
    model_type = _resolve_model_type(req=req, deps=deps, payload=payload)
    task_kind, calibration_method = _resolve_task_and_calibration(model_type=model_type, payload=payload)
    _validate_predict_task(task_kind=task_kind, calibration_method=calibration_method)
    base_proba = predict_proba_from_payload(payload, df_feat)
    p_place = _apply_calibration(
        base_proba=np.asarray(base_proba, dtype=float),
        calibration_method=calibration_method,
        payload=payload,
        df_feat=df_feat,
    )

    df_odds = deps.inference_repository.load_odds(from_date=from_date, to_date=to_date)
    df_race_info = deps.inference_repository.load_race_info(from_date=from_date, to_date=to_date)
    race_entries, edge_candidates = _build_output_frames(
        df_feat=df_feat,
        probability=np.asarray(p_place, dtype=float),
        df_odds=df_odds,
        df_race_info=df_race_info,
        req=req,
    )

    shifted_race_entries: pd.DataFrame | None = None
    shifted_edge_candidates: pd.DataFrame | None = None
    if calibration_method is CalibrationMethod.PLATT_LOGODDS:
        p_place_shift = _apply_place_logit_shift(df_feat=df_feat, p_place=np.asarray(p_place, dtype=float))
        shifted_race_entries, shifted_edge_candidates = _build_output_frames(
            df_feat=df_feat,
            probability=p_place_shift,
            df_odds=df_odds,
            df_race_info=df_race_info,
            req=req,
        )

    return PredictPlaceResult(
        from_date=from_date,
        to_date=to_date,
        race_entries=race_entries,
        edge_candidates=edge_candidates,
        shifted_race_entries=shifted_race_entries,
        shifted_edge_candidates=shifted_edge_candidates,
    )
