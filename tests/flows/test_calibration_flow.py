from unittest.mock import create_autospec

import numpy as np
import pandas as pd
import pytest

from harp.core.training.dataset_builder import BinaryDataset
from harp.interface.ports.calibration_ports import CalibrationReportPort, CalibrationSource, CalibrationSourcePort
from harp.usecase.calibration import CalibrationDeps, CalibrationRequest, run_calibration_usecase


class ProbabilityModel:
    """Controlled model runtime: first input column is its fixed probability."""
    def predict_proba(self, features):
        p = np.asarray(features)[:, 0].astype(float)
        return np.column_stack([1-p, p])


def payload():
    return {"model": ProbabilityModel(), "model_type": "place", "feature_names": ["p"],
            "cat_features": [], "split_info": {"train_year_start": 2020, "train_year_end": 2022, "test_year": 2023}}


def publication():
    writer = create_autospec(CalibrationReportPort, instance=True, spec_set=True)
    published = {}
    def save(report, path):
        published[path] = report
        return {"plot": path + "/calibration.png"}
    writer.save.side_effect = save
    return writer, published


def test_saved_model_and_dataset_select_holdout_and_publish_source_identity():
    source = create_autospec(CalibrationSourcePort, instance=True, spec_set=True)
    source.load.return_value = CalibrationSource(payload(), pd.DataFrame({
        "held_year": [2020, 2022, 2023, 2023], "p": [.99, .99, .2, .8], "is_place": [0, 0, 0, 1]}),
        {"model_sha256": "model-hash", "dataset_sha256": "data-hash"})
    writer, published = publication()
    result = run_calibration_usecase(CalibrationRequest("model.pkl", "data.parquet", "/report"), CalibrationDeps(writer, source))
    assert result.report.metrics["samples"] == 2
    assert result.report.metrics["brier"] == pytest.approx(.04)
    assert published["/report"].metadata["dataset_sha256"] == "data-hash"
    assert result.files["plot"] == "/report/calibration.png"


def test_loaded_binary_dataset_aligns_labels_by_row_identity():
    frame = pd.DataFrame({"p": [.2, .8]}, index=["a", "b"])
    labels = pd.Series([1, 0], index=["b", "a"])
    dataset = BinaryDataset(frame, labels, frame, labels, frame, labels, ["p"], [], {})
    writer, _ = publication()
    result = run_calibration_usecase(CalibrationRequest(payload(), dataset, "/report"), CalibrationDeps(writer))
    assert result.report.metrics["brier"] == pytest.approx(.04)


def test_platt_uses_saved_coefficients_and_odds_without_fitting():
    model = payload()
    model["calibration"] = {"method": "platt_logodds", "params": {
        "odds_col": "win_odds", "platt": {"coef": [0, 0], "intercept": [0]}}}
    writer, _ = publication()
    frame = pd.DataFrame({"p": [.1, .9], "is_place": [0, 1], "win_odds": [2., 3.]})
    result = run_calibration_usecase(CalibrationRequest(model, frame, "/report", split="all", probability="platt"), CalibrationDeps(writer))
    assert result.report.bins.mean_probability.tolist() == [.5]
    assert result.report.metrics["brier"] == .25


@pytest.mark.parametrize("case", ["unknown_split", "race_crosses_split", "missing_odds", "invalid_probability"])
def test_rejected_evaluation_does_not_publish_a_report(case):
    model = payload()
    frame = pd.DataFrame({"race_id": ["r", "r"], "p": [.1, .9], "is_place": [0, 1], "split": ["test", "test"]})
    probability = "raw"
    if case == "unknown_split":
        frame.loc[0, "split"] = "validation_typo"
    elif case == "race_crosses_split":
        frame.loc[0, "split"] = "train"
    elif case == "missing_odds":
        probability = "platt"
        model["calibration"] = {"method": "platt_logodds", "params": {"odds_col": "win_odds"}}
    else:
        frame.loc[0, "p"] = 2
    writer, published = publication()
    with pytest.raises((ValueError, KeyError)):
        run_calibration_usecase(CalibrationRequest(model, frame, "/report", probability=probability), CalibrationDeps(writer))
    assert not published


def test_prediction_replay_keeps_original_split_and_adds_odds_metrics_without_a_model():
    from harp.core.calibration_prediction import CalibrationPredictions
    from harp.interface.ports.calibration_ports import CalibrationPredictionsPort
    from tests.calibration_support import odds_inputs, samples
    predictions = create_autospec(CalibrationPredictionsPort, instance=True, spec_set=True)
    predictions.load.return_value = CalibrationPredictions(samples([.1, .9], [0, 1]),
        {"split": "validation", "target": "is_place", "checkpoint_id": "frozen", "probability": "raw"})
    writer, published = publication()
    req = CalibrationRequest(None, None, "/report", predictions_report="/old-report", odds=odds_inputs([2, 4]).odds)
    result = run_calibration_usecase(req, CalibrationDeps(writer, predictions_store=predictions))
    assert published["/report"].metadata["split"] == "validation"
    assert result.report.metadata["checkpoint_id"] == "frozen"
    assert result.report.odds_bands.metrics.samples.sum() == 2
    assert result.report.metrics["brier"] == pytest.approx(.01)


def test_capture_odds_preserves_unavailable_entries_in_the_published_snapshot():
    from harp.core.calibration_prediction import CalibrationPredictions
    from harp.core.odds import OddsPolicy
    from harp.interface.ports.calibration_ports import CalibrationPredictionsPort
    from harp.interface.ports.repository_ports import TrainingRepositoryPort
    from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort
    from harp.usecase.calibration_odds import CaptureCalibrationOddsDeps, CaptureCalibrationOddsRequest, run_capture_calibration_odds_usecase
    from tests.calibration_support import odds_inputs, samples
    predictions = create_autospec(CalibrationPredictionsPort, instance=True, spec_set=True)
    predictions.load.return_value = CalibrationPredictions(samples([.1, .9], [0, 1]), {"predictions_sha256": "frozen"})
    repository = create_autospec(TrainingRepositoryPort, instance=True, spec_set=True)
    repository.load_training_input.return_value = odds_inputs([2, np.nan])
    snapshots = create_autospec(PredictionSnapshotStorePort, instance=True, spec_set=True)
    saved = {}
    def save(inputs, metadata):
        saved["inputs"], saved["metadata"] = inputs, metadata
        return "snapshot"
    snapshots.save.side_effect = save
    result = run_capture_calibration_odds_usecase(CaptureCalibrationOddsRequest("/predictions",
        OddsPolicy.pre_start(minutes=10, max_age_seconds=300)), CaptureCalibrationOddsDeps(predictions, repository, snapshots))
    assert result.matched_entries == 2
    assert saved["inputs"].odds.frame.place_status.tolist() == ["available", "unavailable"]
    assert saved["metadata"]["predictions_sha256"] == "frozen"
