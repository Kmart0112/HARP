import json

import numpy as np
import pytest
pytest.importorskip("torch")

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_model_store import TorchNnModelStore
from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
from harp.controllers.calibration import export_calibration_report
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe
from harp.usecase.prediction.nn import load_nn_predictor
from harp.usecase.training.nn import run_nn_train_usecase
from harp.usecase.training.nn_dto import NnTrainRequest
from tests.nn_dataset_support import win_dataset_inputs
from tests.nn_training_support import rank_recipe, small_prepared, training_deps, torch_cpu_runtime


def test_rank_bundle_restores_main_predictions_and_exports_calibration_without_db(tmp_path):
    source = win_dataset_inputs()
    prepared = small_prepared(source)
    deps, _, _ = training_deps(source)
    input_id = ParquetNnDatasetStore(tmp_path / "inputs").save(source, {})
    dataset_id = JsonNnPreparedDatasetStore(tmp_path / "datasets").save(NnPreparedDatasetRecipe(
        input_id, prepared.config, prepared.preprocessing, prepared.partitions))
    result = run_nn_train_usecase(NnTrainRequest(dataset_id, rank_recipe(), "cpu", {"source": "fixture"}), deps)
    expected = load_nn_predictor(result.run_id, deps.model_store).predict(source.inputs)
    saved = deps.model_store.load_checkpoint(result.run_id)
    store = TorchNnModelStore(tmp_path / "models")
    run_id = store.create_run(saved.metadata)
    checkpoint_id = store.save_checkpoint(run_id, saved.checkpoint)
    restored = load_nn_predictor(run_id, TorchNnModelStore(tmp_path / "models"))
    np.testing.assert_array_equal(restored.predict(source.inputs).place_probability, expected.place_probability)
    report = export_calibration_report(model=run_id, dataset=dataset_id, backend="nn", split="validation",
        output_dir=tmp_path / "report", input_root=tmp_path / "inputs",
        prepared_root=tmp_path / "datasets", model_root=tmp_path / "models")
    metadata = json.loads((tmp_path / "report/metrics.json").read_text())["metadata"]
    assert metadata["checkpoint_id"] == checkpoint_id
    assert report.report.metrics["samples"] == 2
    assert (tmp_path / "report/calibration.png").is_file()
