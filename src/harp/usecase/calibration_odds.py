"""Capture evaluation odds through the existing logical input and snapshot Ports."""
from dataclasses import dataclass

import pandas as pd

from harp.core.odds import OddsPolicy, normalize_entry_keys
from harp.core.odds_calibration import validate_odds_entry_identity
from harp.core.race_inputs import RaceInputQuery
from harp.interface.ports.calibration_ports import CalibrationPredictionsPort
from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort
from harp.interface.ports.repository_ports import TrainingRepositoryPort


@dataclass(frozen=True)
class CaptureCalibrationOddsRequest:
    predictions_report: str
    policy: OddsPolicy


@dataclass(frozen=True)
class CaptureCalibrationOddsDeps:
    predictions: CalibrationPredictionsPort
    repository: TrainingRepositoryPort
    snapshots: PredictionSnapshotStorePort


@dataclass(frozen=True)
class CaptureCalibrationOddsResult:
    snapshot_id: str
    prediction_entries: int
    matched_entries: int
    policy: dict


def run_capture_calibration_odds_usecase(req: CaptureCalibrationOddsRequest,
                                        deps: CaptureCalibrationOddsDeps) -> CaptureCalibrationOddsResult:
    saved = deps.predictions.load(req.predictions_report)
    entries = normalize_entry_keys(saved.samples, name="evaluation entries")
    if entries.empty or "held_date" not in entries:
        raise ValueError("odds preparation requires nonempty predictions with held_date")
    dates = pd.to_datetime(entries.held_date, errors="raise")
    if dates.isna().any():
        raise ValueError("prediction held_date is missing")
    query = RaceInputQuery(dates.min().date().isoformat(), dates.max().date().isoformat(),
                           feature_names=("kettonum",), categorical_features=("kettonum",),
                           odds_policy=req.policy, filters={"race_id__in": entries.race_id.unique().tolist()})
    inputs = deps.repository.load_training_input(query)
    inputs.validate_query(query)
    if not inputs.frame.race_id.isin(entries.race_id).all():
        raise ValueError("odds provider returned an unrequested race")
    validate_odds_entry_identity(entries, inputs.frame)
    matched = entries[["race_id", "horse_number"]].merge(inputs.frame[["race_id", "horse_number"]],
                on=["race_id", "horse_number"], validate="one_to_one")
    snapshot_id = deps.snapshots.save(inputs, {"purpose": "calibration_evaluation_odds",
                                     "predictions_sha256": saved.metadata.get("predictions_sha256"),
                                     "prediction_entries": len(entries), "matched_entries": len(matched)})
    return CaptureCalibrationOddsResult(snapshot_id, len(entries), len(matched), req.policy.to_dict())
