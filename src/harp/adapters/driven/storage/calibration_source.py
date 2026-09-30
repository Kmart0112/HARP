"""Restore supported file artifacts; no training or database dependency."""
from hashlib import sha256
from pathlib import Path

import pandas as pd

from harp.interface.ports.calibration_ports import CalibrationSource

from .artifact_store import PickleModelLoaderAdapter


class TabularCalibrationSource:
    def load(self, model: str, dataset: str, *, checkpoint_id=None) -> CalibrationSource:
        if checkpoint_id is not None:
            raise ValueError("checkpoint_id is only supported for NN")
        payload = PickleModelLoaderAdapter().load_model_payload(model)
        path = Path(dataset).resolve()
        # Hash the bytes actually parsed, even if the source path is later replaced.
        import io
        raw = path.read_bytes()
        if path.suffix.lower() == ".parquet":
            frame = pd.read_parquet(io.BytesIO(raw))
        else:
            raise ValueError("tabular calibration dataset must be a Parquet file")
        return CalibrationSource(payload, frame, {"source": "files", "model": str(Path(model).resolve()),
                                 "model_sha256": payload["artifact_sha256"], "dataset": str(path),
                                 "dataset_sha256": sha256(raw).hexdigest()})


class NnCalibrationSource:
    def __init__(self, input_root, prepared_root, model_root, device):
        from .nn_dataset_store import ParquetNnDatasetStore
        from .nn_model_store import TorchNnModelStore
        from .nn_prepared_dataset_store import JsonNnPreparedDatasetStore
        self.inputs = ParquetNnDatasetStore(input_root)
        self.prepared = JsonNnPreparedDatasetStore(prepared_root)
        self.models = TorchNnModelStore(model_root)
        self.device = device

    def load(self, model: str, dataset: str, *, checkpoint_id=None) -> CalibrationSource:
        from harp.core.nn.dataset import restore_nn_dataset
        from harp.core.nn.prediction import NnPredictor
        saved = self.models.load_checkpoint(model, checkpoint_id)
        recipe = self.prepared.load(dataset)
        inputs = self.inputs.load(recipe.input_dataset_id).inputs
        restored = restore_nn_dataset(inputs, recipe.config, recipe.preprocessing, recipe.partitions)
        predictor = NnPredictor.from_weights(saved.preprocessing, saved.recipe.model,
                                            saved.checkpoint["best_weights"], saved.metadata["history_length"], self.device,
                                            task=saved.recipe.task, auxiliary_rank=saved.recipe.auxiliary_rank,
                                            auxiliary_odds=saved.recipe.auxiliary_odds)
        return CalibrationSource(predictor, restored, {"source": "files", "run_id": model,
                                 "checkpoint_id": saved.checkpoint_id, "best_epoch": saved.checkpoint["best_epoch"],
                                 "prepared_dataset_id": dataset, "input_dataset_id": recipe.input_dataset_id,
                                 "training_dataset_id": saved.metadata["prepared_dataset_id"]})
