import numpy as np
import pytest

pytest.importorskip("torch")

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_model_store import TorchNnModelStore
from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
from harp.controllers.calibration import export_calibration_report
from harp.core.nn.split import NnDatasetConfig
from harp.usecase.nn_dataset.dto import NnDatasetDeps, PrepareNnDatasetRequest
from harp.usecase.nn_dataset.prepare import load_prepared_nn_dataset, run_prepare_nn_dataset_usecase
from harp.usecase.prediction.nn import load_nn_predictor
from harp.usecase.training.nn import run_nn_train_usecase
from harp.usecase.training.nn_dto import NnTrainDeps, NnTrainRequest
from tests.nn_dataset_support import win_dataset_inputs
from tests.nn_training_support import small_recipe, torch_cpu_runtime


def test_saved_win_dataset_and_model_restore_task_predictions_and_calibration_without_db(tmp_path):
    source = win_dataset_inputs()
    inputs = ParquetNnDatasetStore(tmp_path / "inputs")
    datasets = JsonNnPreparedDatasetStore(tmp_path / "datasets")
    models = TorchNnModelStore(tmp_path / "models")
    input_id = inputs.save(source, {})
    deps = NnDatasetDeps(inputs, datasets)
    result = run_prepare_nn_dataset_usecase(PrepareNnDatasetRequest(
        NnDatasetConfig("2026-06-13", "2026-06-20", 3, task="win"), input_dataset_id=input_id), deps)
    prepared = load_prepared_nn_dataset(result.prepared_dataset_id, deps)
    assert prepared.split("train")[0]["labels"].tolist() == [1, 0]
    recipe = small_recipe(task="win", **{"loss.name": "cross_entropy", "loss.reduction": "race_mean"})
    trained = run_nn_train_usecase(NnTrainRequest(result.prepared_dataset_id, recipe, "cpu", {}),
                                  NnTrainDeps(inputs, datasets, models))
    predictor = load_nn_predictor(trained.run_id, TorchNnModelStore(tmp_path / "models"))
    predictions = predictor.predict(source.inputs)
    assert "win_probability" in predictions and "place_probability" not in predictions
    np.testing.assert_allclose(predictions.groupby("race_id").win_probability.sum(), 1, atol=1e-6)
    report = export_calibration_report(model=trained.run_id, dataset=result.prepared_dataset_id,
        backend="nn", output_dir=tmp_path / "report", input_root=tmp_path / "inputs",
        prepared_root=tmp_path / "datasets", model_root=tmp_path / "models").report
    assert report.metadata["target"] == "is_win"
    assert report.metrics["samples"] == 2
    assert report.metrics["observed_rate"] == .5
    expected = predictions.loc[predictions.race_id.eq("R4"), "win_probability"]
    np.testing.assert_allclose(report.predictions.probability, expected, atol=1e-6)
