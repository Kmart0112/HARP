from harp.adapters.driven.storage.calibration_report import FileCalibrationReport
from harp.adapters.driven.storage.calibration_source import NnCalibrationSource, TabularCalibrationSource
from harp.usecase.calibration import CalibrationDeps
from harp.adapters.driven.storage.calibration_predictions import FileCalibrationPredictions
from harp.adapters.driven.storage.prediction_snapshot_store import ParquetPredictionSnapshotStore


def build_calibration_deps(backend, device, input_root, prepared_root, model_root,
                           odds_root="pipeline/artifacts/evaluation_odds"):
    if backend is None:
        source = None
    elif backend == "lightgbm":
        source = TabularCalibrationSource()
    elif backend == "nn":
        from harp.controllers.training.deps import resolve_nn_device
        source = NnCalibrationSource(input_root, prepared_root, model_root, resolve_nn_device(device))
    else:
        raise ValueError("backend must be lightgbm or nn")
    return CalibrationDeps(FileCalibrationReport(), source, FileCalibrationPredictions(),
                           ParquetPredictionSnapshotStore(odds_root))


def build_calibration_odds_deps(config, odds_root):
    from harp.adapters.driven.db.race_input_repository import SqlRaceInputRepository, mart_input_mapping
    from harp.shared.db import get_engine
    from harp.usecase.calibration_odds import CaptureCalibrationOddsDeps
    return CaptureCalibrationOddsDeps(FileCalibrationPredictions(), SqlRaceInputRepository(
        engine=get_engine(config.database.db_url),
        mapping=mart_input_mapping(config.mart.training_mart_table,
                                   quotes_table=config.mart.training_quotes_table, pre_start_minutes=10)),
        ParquetPredictionSnapshotStore(odds_root))
