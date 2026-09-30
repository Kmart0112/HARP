"""One-call Python and file-based calibration report entry points."""
from os import PathLike

from harp.usecase.calibration import CalibrationRequest, run_calibration_usecase
from .deps import build_calibration_deps
from harp.core.odds_calibration import DEFAULT_CALIBRATION_ODDS_BOUNDS


def export_calibration_report(*, model, dataset, output_dir, split="test", target=None,
                              probability="raw", n_bins=10, strategy="quantile", batch_size=32,
                              backend=None, checkpoint_id=None, device="cpu",
                              input_root="pipeline/artifacts/nn_inputs",
                              prepared_root="pipeline/artifacts/nn_datasets",
                              model_root="pipeline/artifacts/nn_training", entry_metadata=None,
                              odds=None, odds_snapshot_id=None, odds_root="pipeline/artifacts/evaluation_odds",
                              odds_market="place", place_method="midpoint",
                              odds_bounds=DEFAULT_CALIBRATION_ODDS_BOUNDS, min_samples_per_bin=30):
    """Pass loaded objects, or set backend='lightgbm'/'nn' with paths/IDs."""
    if backend is None and (isinstance(model, (str, PathLike)) or isinstance(dataset, (str, PathLike))):
        raise ValueError("file paths or IDs require backend='lightgbm' or backend='nn'")
    deps = build_calibration_deps(backend, device, input_root, prepared_root, model_root, odds_root)
    req = CalibrationRequest(model, dataset, str(output_dir), split, target, probability,
                             n_bins, strategy, batch_size, checkpoint_id, entry_metadata=entry_metadata,
                             odds=odds, odds_snapshot_id=odds_snapshot_id, odds_market=odds_market,
                             place_method=place_method, odds_bounds=tuple(odds_bounds), min_samples_per_bin=min_samples_per_bin)
    return run_calibration_usecase(req, deps)


def reaggregate_calibration_report(*, predictions_report, output_dir, n_bins=10, strategy="quantile",
                                   odds=None, odds_snapshot_id=None, odds_root="pipeline/artifacts/evaluation_odds",
                                   odds_market="place", place_method="midpoint",
                                   odds_bounds=DEFAULT_CALIBRATION_ODDS_BOUNDS, min_samples_per_bin=30):
    deps = build_calibration_deps(None, None, None, None, None, odds_root)
    req = CalibrationRequest(None, None, str(output_dir), predictions_report=str(predictions_report),
                             n_bins=n_bins, strategy=strategy, odds=odds, odds_snapshot_id=odds_snapshot_id,
                             odds_market=odds_market, place_method=place_method, odds_bounds=tuple(odds_bounds),
                             min_samples_per_bin=min_samples_per_bin)
    return run_calibration_usecase(req, deps)


def prepare_calibration_odds(*, config, predictions_report, odds_root="pipeline/artifacts/evaluation_odds",
                             minutes_before_start=10, max_age_seconds=300):
    from harp.core.odds import OddsPolicy
    from harp.usecase.calibration_odds import CaptureCalibrationOddsRequest, run_capture_calibration_odds_usecase
    from .deps import build_calibration_odds_deps
    req = CaptureCalibrationOddsRequest(str(predictions_report), OddsPolicy.pre_start(
        minutes=minutes_before_start, max_age_seconds=max_age_seconds))
    return run_capture_calibration_odds_usecase(req, build_calibration_odds_deps(config, odds_root))
