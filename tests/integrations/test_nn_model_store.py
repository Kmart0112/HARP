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
from tests.nn_training_support import small_prepared, small_recipe, torch_cpu_runtime


def trained_checkpoint():
    prepared, recipe = small_prepared(), small_recipe()
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


def test_model_bundle_restores_predictions_without_the_training_inputs(tmp_path):
    metadata, checkpoint, prepared = trained_checkpoint()
    store = TorchNnModelStore(tmp_path)
    run_id = store.create_run(metadata)
    identity = store.save_checkpoint(run_id, checkpoint)
    restored = TorchNnModelStore(tmp_path).load_checkpoint(run_id)
    assert restored.checkpoint_id == identity
    assert restored.checkpoint["epoch"] == 1
    assert restored.preprocessing == prepared.preprocessing
    model = build_nn_network(NnInputSpec.from_preprocessing(prepared.preprocessing), small_recipe().model)
    model.load_state_dict(checkpoint["best_weights"])
    expected = evaluate_nn(model, prepared.dataset, batch_size=2, device="cpu").predictions
    predictor = load_nn_predictor(run_id, store)
    actual = predictor.predict(dataset_inputs(future_rate=.4).inputs, batch_size=2)
    assert actual[["race_id", "kettonum"]].equals(expected[["race_id", "kettonum"]])
    np.testing.assert_array_equal(actual.place_probability, expected.place_probability)


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
