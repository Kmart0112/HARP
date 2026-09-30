import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from harp.adapters.driven.storage.artifact_store import PickleArtifactStoreAdapter
from harp.controllers.calibration import export_calibration_report


def test_saved_categorical_lightgbm_roundtrip_exports_headless_report(tmp_path):
    train = pd.DataFrame({"category": pd.Categorical(["a", "b"] * 12), "x": [0., 1.] * 12})
    target = np.array([0, 1] * 12)
    model = lgb.LGBMClassifier(n_estimators=3, min_child_samples=1, n_jobs=1, verbosity=-1).fit(train, target)
    artifact = tmp_path / "model.pkl"
    PickleArtifactStoreAdapter().save_artifact({"model": model, "model_type": "win",
        "feature_names": ["category", "x"], "cat_features": ["category"]}, str(artifact))
    # Includes unseen category, reordered category vocabulary, and only evaluation rows.
    frame = pd.DataFrame({"category": pd.Categorical(["b", "unseen", "a"], categories=["unseen", "b", "a"]),
                          "x": [1., 0., 0.], "is_win": [1, 0, 0]})
    expected = model.predict_proba(frame[["category", "x"]])[:, 1]
    data = tmp_path / "eval.parquet"
    frame.to_parquet(data)
    result = export_calibration_report(model=str(artifact), dataset=str(data), backend="lightgbm",
                                       split="all", output_dir=tmp_path / "report")
    document = json.loads((tmp_path / "report/metrics.json").read_text())
    assert document["metrics"]["brier"] == pytest.approx(np.mean((expected - frame.is_win.to_numpy())**2))
    assert len(document["metadata"]["model_sha256"]) == 64
    assert len(document["metadata"]["dataset_sha256"]) == 64
    assert pd.read_csv(result.files["bins"])["count"].sum() == 3
    assert (tmp_path / "report/calibration.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    before = (tmp_path / "report/metrics.json").read_bytes()
    with pytest.raises(FileExistsError):
        export_calibration_report(model=str(artifact), dataset=str(data), backend="lightgbm",
                                  split="all", output_dir=tmp_path / "report")
    assert (tmp_path / "report/metrics.json").read_bytes() == before


def test_prediction_and_odds_snapshots_replay_without_model_and_detect_corruption(tmp_path):
    from harp.adapters.driven.storage.calibration_predictions import FileCalibrationPredictions
    from harp.adapters.driven.storage.calibration_report import FileCalibrationReport
    from harp.adapters.driven.storage.prediction_snapshot_store import ParquetPredictionSnapshotStore
    from harp.controllers.calibration import reaggregate_calibration_report
    from harp.core.calibration import calculate_calibration
    from tests.calibration_support import odds_inputs, samples
    original = tmp_path / "original"
    FileCalibrationReport().save(calculate_calibration(samples([.1, .9], [0, 1]),
        metadata={"split": "test", "target": "is_place", "checkpoint_id": "saved", "probability": "raw"}), str(original))
    store = ParquetPredictionSnapshotStore(tmp_path / "odds")
    identity = store.save(odds_inputs([1.4, np.nan]), {"purpose": "evaluation"})
    result = reaggregate_calibration_report(predictions_report=original, output_dir=tmp_path / "regrouped",
        odds_snapshot_id=identity, odds_root=tmp_path / "odds", odds_bounds=(1, 2, float("inf")))
    assert result.report.metrics["samples"] == 2
    assert result.report.odds_bands.metrics.samples.tolist() == [1, 0]
    doc = json.loads((tmp_path / "regrouped/metrics.json").read_text())
    assert doc["odds_bands"]["metadata"]["snapshot_id"] == identity
    assert (tmp_path / "regrouped/odds_band_calibration.png").read_bytes().startswith(b"\x89PNG")
    reloaded = FileCalibrationPredictions().load(str(tmp_path / "regrouped"))
    assert reloaded.metadata["checkpoint_id"] == "saved"
    assert reloaded.samples.probability.tolist() == [.1, .9]
    (original / "predictions.parquet").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        FileCalibrationPredictions().load(str(original))
