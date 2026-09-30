from dataclasses import dataclass

from harp.core.calibration import CalibrationReport
from harp.core.calibration import calculate_calibration
from harp.core.calibration_prediction import evaluate_calibration
from harp.core.odds_calibration import DEFAULT_CALIBRATION_ODDS_BOUNDS, add_odds_band_report, validate_odds_entry_identity
from harp.interface.ports.calibration_ports import CalibrationPredictionsPort, CalibrationReportPort, CalibrationSourcePort
from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort


@dataclass(frozen=True)
class CalibrationRequest:
    model: object
    dataset: object
    output_dir: str
    split: str = "test"
    target: str | None = None
    probability: str = "raw"
    n_bins: int = 10
    strategy: str = "quantile"
    batch_size: int = 32
    checkpoint_id: str | None = None
    predictions_report: str | None = None
    odds_snapshot_id: str | None = None
    odds: object | None = None
    odds_market: str = "place"
    place_method: str = "midpoint"
    odds_bounds: tuple[float, ...] = DEFAULT_CALIBRATION_ODDS_BOUNDS
    min_samples_per_bin: int = 30
    entry_metadata: object | None = None


@dataclass(frozen=True)
class CalibrationDeps:
    writer: CalibrationReportPort
    source: CalibrationSourcePort | None = None
    predictions_store: CalibrationPredictionsPort | None = None
    odds_store: PredictionSnapshotStorePort | None = None


@dataclass(frozen=True)
class CalibrationResult:
    report: CalibrationReport
    files: dict[str, str]


def run_calibration_usecase(req: CalibrationRequest, deps: CalibrationDeps) -> CalibrationResult:
    if req.odds is not None and req.odds_snapshot_id is not None:
        raise ValueError("choose odds object or odds snapshot, not both")
    model, dataset, metadata = req.model, req.dataset, {"source": "in_memory"}
    if req.predictions_report is not None:
        if model is not None or dataset is not None or deps.source is not None or req.checkpoint_id is not None:
            raise ValueError("prediction replay cannot also load a model or dataset")
        if deps.predictions_store is None:
            raise ValueError("prediction replay requires a prediction store")
        restored = deps.predictions_store.load(req.predictions_report)
        report = calculate_calibration(restored.samples, n_bins=req.n_bins, strategy=req.strategy, metadata=restored.metadata)
    else:
        if deps.source is not None:
            loaded = deps.source.load(model, dataset, checkpoint_id=req.checkpoint_id)
            model, dataset, metadata = loaded.model, loaded.dataset, loaded.metadata
        report = evaluate_calibration(model, dataset, split=req.split, target=req.target,
                                      probability=req.probability, n_bins=req.n_bins, strategy=req.strategy,
                                      batch_size=req.batch_size, metadata=metadata, entry_metadata=req.entry_metadata)
    odds, odds_metadata = req.odds, {"source": "in_memory"}
    if req.odds_snapshot_id is not None:
        if deps.odds_store is None:
            raise ValueError("odds snapshot requires an odds store")
        snapshot = deps.odds_store.load(req.odds_snapshot_id)
        validate_odds_entry_identity(report.predictions, snapshot.inputs.frame)
        odds = snapshot.inputs.odds
        odds_metadata = {"snapshot_id": req.odds_snapshot_id, "source_revision": snapshot.inputs.source_revision,
                         "captured_at": snapshot.inputs.captured_at.isoformat() if snapshot.inputs.captured_at else None}
    if odds is not None:
        report = add_odds_band_report(report, odds, market=req.odds_market, place_method=req.place_method,
                                      bounds=req.odds_bounds, min_samples_per_bin=req.min_samples_per_bin,
                                      odds_metadata=odds_metadata)
    return CalibrationResult(report, deps.writer.save(report, req.output_dir))
