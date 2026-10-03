from dataclasses import asdict

import numpy as np
import pytest
pytest.importorskip("torch")

from harp.adapters.driven.storage.nn_model_store import TorchNnModelStore
from harp.adapters.driven.storage.nn_training_recipe import YamlNnTrainingRecipeReader
from harp.core.nn.config import resolve_nn_training_recipe
from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.networks.factory import build_nn_network
from harp.core.nn.tensor_batch import NnInputSpec
from harp.core.nn.training import capture_nn_checkpoint, evaluate_nn, initialize_nn_training, train_one_nn_epoch, update_nn_selection
from harp.usecase.prediction.nn import load_nn_predictor
from tests.nn_dataset_support import dataset_inputs
from tests.nn_opponent_support import opponent_inputs
from tests.nn_performance_support import performance_inputs
from tests.nn_training_support import nn_architecture, small_prepared, small_recipe, torch_cpu_runtime


def trained_checkpoint(inputs=None, architecture="history_set_transformer_v1"):
    prepared, recipe = small_prepared(inputs), small_recipe(**{"model.name": architecture})
    spec = NnInputSpec.from_preprocessing(prepared.preprocessing)
    state = initialize_nn_training(spec, recipe, "cpu")
    train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
    evaluation = evaluate_nn(state.model, prepared.split("validation"), batch_size=2, device="cpu")
    update_nn_selection(state, evaluation, recipe)
    state.metrics_history.append({"epoch": state.epoch, "validation": evaluation.metrics})
    metadata = {"recipe": asdict(recipe), "preprocessing": asdict(prepared.preprocessing),
                "input_spec": asdict(spec), "history_length": prepared.config.history_length,
                "prepared_dataset_id": "a" * 64}
    return metadata, capture_nn_checkpoint(state, "cpu"), prepared


@pytest.mark.parametrize("input_factory", [dataset_inputs, opponent_inputs, performance_inputs])
def test_model_bundle_restores_predictions_without_the_training_inputs(tmp_path, input_factory, nn_architecture):
    inputs = input_factory()
    metadata, checkpoint, prepared = trained_checkpoint(inputs, nn_architecture)
    store = TorchNnModelStore(tmp_path)
    run_id = store.create_run(metadata)
    identity = store.save_checkpoint(run_id, checkpoint)
    restored = TorchNnModelStore(tmp_path).load_checkpoint(run_id)
    assert restored.checkpoint_id == identity
    assert restored.checkpoint["epoch"] == 1
    assert restored.preprocessing == prepared.preprocessing
    assert restored.recipe.model.name == nn_architecture
    model = build_nn_network(NnInputSpec.from_preprocessing(prepared.preprocessing),
                             small_recipe(**{"model.name": nn_architecture}).model)
    model.load_state_dict(checkpoint["best_weights"])
    expected = evaluate_nn(model, prepared.dataset, batch_size=2, device="cpu").predictions
    predictor = load_nn_predictor(run_id, store)
    actual = predictor.predict(inputs.inputs, batch_size=2)
    assert actual[["race_id", "kettonum"]].equals(expected[["race_id", "kettonum"]])
    np.testing.assert_array_equal(actual.place_probability, expected.place_probability)
    if input_factory is not dataset_inputs:
        with pytest.raises(NnInputContractError, match="feature order"):
            predictor.predict(dataset_inputs(future_rate=.4).inputs, batch_size=2)


def test_nn_calibration_loads_explicit_dataset_and_publishes_checkpoint_identity(tmp_path):
    import json
    from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
    from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
    from harp.controllers.calibration import export_calibration_report
    from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe
    metadata, checkpoint, prepared = trained_checkpoint()
    input_id = ParquetNnDatasetStore(tmp_path / "inputs").save(dataset_inputs(future_rate=.4), {})
    dataset_id = JsonNnPreparedDatasetStore(tmp_path / "datasets").save(NnPreparedDatasetRecipe(
        input_id, prepared.config, prepared.preprocessing, prepared.partitions))
    # The evaluation dataset identity may differ; its fitted contract must match.
    store = TorchNnModelStore(tmp_path / "models")
    run_id = store.create_run(metadata)
    checkpoint_id = store.save_checkpoint(run_id, checkpoint)
    result = export_calibration_report(model=run_id, dataset=dataset_id, backend="nn",
        output_dir=tmp_path / "report", input_root=tmp_path / "inputs",
        prepared_root=tmp_path / "datasets", model_root=tmp_path / "models")
    document = json.loads((tmp_path / "report/metrics.json").read_text())
    assert document["metadata"]["checkpoint_id"] == checkpoint_id
    assert document["metadata"]["prepared_dataset_id"] == dataset_id
    assert result.report.metrics["samples"] == 1
    assert result.report.metrics["observed_rate"] == 1
    assert result.report.predictions[["race_id", "kettonum", "horse_number"]].to_dict("records") == [
        {"race_id": "R4", "kettonum": "H3", "horse_number": 1}]


@pytest.mark.parametrize("file", ["best_weights.pt", "last_checkpoint.pt", "metadata.json", "manifest.json"])
def test_model_bundle_rejects_corruption_before_loading_weights(tmp_path, file):
    metadata, checkpoint, _ = trained_checkpoint()
    store = TorchNnModelStore(tmp_path)
    run_id = store.create_run(metadata)
    identity = store.save_checkpoint(run_id, checkpoint)
    path = tmp_path / run_id / "checkpoints" / identity / file
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(NnInputContractError, match="integrity"):
        store.load_checkpoint(run_id)


def test_failed_save_does_not_advance_the_last_published_checkpoint(tmp_path):
    metadata, checkpoint, _ = trained_checkpoint()
    store = TorchNnModelStore(tmp_path)
    run_id = store.create_run(metadata)
    identity = store.save_checkpoint(run_id, checkpoint)
    checkpoint["epoch"] = 2
    checkpoint["metrics_history"].append({"validation": float("nan")})
    with pytest.raises(ValueError):
        store.save_checkpoint(run_id, checkpoint)
    assert store.load_checkpoint(run_id).checkpoint_id == identity
    assert not list((tmp_path / run_id / "checkpoints").glob(".pending-*"))


def test_yaml_overrides_change_the_effective_training_configuration_and_reject_typos(tmp_path):
    import yaml
    path = tmp_path / "recipe.yml"
    path.write_text(yaml.safe_dump(asdict(small_recipe())))
    reader = YamlNnTrainingRecipeReader()
    recipe = resolve_nn_training_recipe(reader.load(str(path)), reader.parse_overrides(("optimizer.lr=3e-4", "training.seed=43")))
    assert recipe.optimizer.lr == .0003
    assert recipe.training.seed == 43
    with pytest.raises(NnInputContractError, match="unknown NN override"):
        resolve_nn_training_recipe(reader.load(str(path)), reader.parse_overrides(("optimizer.learning_rat=0.1",)))
    path.write_text("version: 1\nversion: 2\n")
    with pytest.raises(NnInputContractError, match="duplicate"):
        reader.load(str(path))
