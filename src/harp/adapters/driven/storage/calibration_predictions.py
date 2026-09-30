"""Restore the predictions and provenance published by FileCalibrationReport."""
from hashlib import sha256
import io
import json
from pathlib import Path

import pandas as pd

from harp.core.calibration_prediction import CalibrationPredictions


class FileCalibrationPredictions:
    def load(self, report_dir: str) -> CalibrationPredictions:
        root = Path(report_dir)
        manifest = json.loads((root / "manifest.json").read_text())
        if manifest.get("version") != 1 or manifest.get("kind") != "calibration_report":
            raise ValueError("unsupported calibration report manifest")
        contents = {}
        for name in ("predictions.parquet", "metrics.json"):
            raw = (root / name).read_bytes()
            if sha256(raw).hexdigest() != manifest["files"].get(name):
                raise ValueError("calibration predictions/provenance integrity failure")
            contents[name] = raw
        metadata = json.loads(contents["metrics.json"])["metadata"]
        return CalibrationPredictions(pd.read_parquet(io.BytesIO(contents["predictions.parquet"])),
                                      {**metadata, "predictions_sha256": manifest["files"]["predictions.parquet"]})
