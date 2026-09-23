from dataclasses import fields

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from harp.core.nn.dataset import collate_nn_races
from harp.core.nn.losses import nn_place_loss
from harp.core.nn.tensor_batch import NnInputSpec, NnModelInputs
from harp.core.nn.training import (
    capture_nn_checkpoint, evaluate_nn, initialize_nn_training, restore_nn_checkpoint,
    train_one_nn_epoch, update_nn_selection,
)
from tests.nn_training_support import small_prepared, small_recipe, torch_cpu_runtime


def network_and_batch():
    prepared = small_prepared()
    state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), small_recipe(), "cpu")
    state.model.eval()
    batch = collate_nn_races([prepared.dataset[0], prepared.dataset[1]])
    return state.model, batch


def test_transformer_predictions_follow_horses_when_the_field_is_permuted():
    model, batch = network_and_batch()
    features = NnModelInputs.from_numpy(batch, "cpu")
    permuted = NnModelInputs(**{field.name: getattr(features, field.name)[:, [1, 0]] for field in fields(features)})
    with torch.inference_mode():
        expected = model(features)[:, [1, 0]]
        actual = model(permuted)
    torch.testing.assert_close(actual, expected, atol=1e-6, rtol=1e-6)


def test_extra_padding_and_arbitrary_padded_values_cannot_change_real_horse_predictions():
    model, batch = network_and_batch()
    with torch.inference_mode():
        expected = model(NnModelInputs.from_numpy(batch, "cpu"))
    padded = {}
    for key, value in batch.items():
        if not isinstance(value, np.ndarray):
            continue
        widths = [(0, 0), (0, 2)] + [(0, 0)] * (value.ndim - 2)
        if key.startswith("history_"):
            widths[2] = (0, 2)
        padded[key] = np.pad(value, widths)
    # Invalid category IDs would fail embedding lookup if masked slots leaked in.
    for name in ("current_numeric", "current_categorical"):
        padded[name][~padded["entrant_mask"]] = 99999
    for name in ("history_numeric", "history_categorical", "history_relative"):
        padded[name][~padded["history_mask"]] = 99999
    with torch.inference_mode():
        actual = model(NnModelInputs.from_numpy(padded, "cpu"))
    torch.testing.assert_close(actual[:, :2], expected, atol=1e-6, rtol=1e-6)
    assert not actual[:, 2:].any()


def test_new_horses_have_finite_predictions_and_gradients_and_unknown_labels_are_ignored():
    model, batch = network_and_batch()
    model.train()
    features = NnModelInputs.from_numpy(batch, "cpu")
    logits = model(features)
    labels = torch.as_tensor(batch["labels"])
    mask = torch.as_tensor(batch["label_mask"])
    assert not features.history_mask[0, 1].any()  # Real debutant, not a padded horse.
    loss = nn_place_loss(logits, labels, features.entrant_mask, mask)
    changed = labels.clone()
    changed[~mask] = float("nan")
    torch.testing.assert_close(nn_place_loss(logits, changed, features.entrant_mask, mask), loss)
    loss.backward()
    assert torch.isfinite(logits).all()
    assert all(torch.isfinite(parameter.grad).all() for parameter in model.parameters() if parameter.grad is not None)


def test_training_can_learn_a_tiny_field_and_metrics_ignore_batch_padding():
    prepared, recipe = small_prepared(), small_recipe()
    state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, "cpu")
    train = prepared.split("train")
    before = evaluate_nn(state.model, train, batch_size=1, device="cpu")
    for _ in range(15):
        train_one_nn_epoch(state, train, recipe, "cpu")
    after = evaluate_nn(state.model, train, batch_size=1, device="cpu")
    assert after.metrics["logloss"] < before.metrics["logloss"] * .5
    one = evaluate_nn(state.model, prepared.dataset, batch_size=1, device="cpu")
    many = evaluate_nn(state.model, prepared.dataset, batch_size=3, device="cpu")
    assert many.metrics["entries"] == 4
    assert many.metrics["logloss"] == pytest.approx(one.metrics["logloss"], abs=1e-6)
    np.testing.assert_allclose(many.predictions.place_probability, one.predictions.place_probability, atol=1e-6)


def test_checkpoint_resume_matches_uninterrupted_training_with_dropout():
    prepared, recipe = small_prepared(), small_recipe(**{"model.dropout": .2})
    spec = NnInputSpec.from_preprocessing(prepared.preprocessing)
    state = initialize_nn_training(spec, recipe, "cpu")
    train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
    validation = evaluate_nn(state.model, prepared.split("validation"), batch_size=2, device="cpu")
    update_nn_selection(state, validation, recipe)
    checkpoint = capture_nn_checkpoint(state, "cpu")
    train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
    uninterrupted = evaluate_nn(state.model, prepared.dataset, batch_size=2, device="cpu")
    resumed = initialize_nn_training(spec, recipe, "cpu")
    restore_nn_checkpoint(resumed, checkpoint, "cpu")
    train_one_nn_epoch(resumed, prepared.split("train"), recipe, "cpu")
    actual = evaluate_nn(resumed.model, prepared.dataset, batch_size=2, device="cpu")
    np.testing.assert_array_equal(actual.predictions.place_probability, uninterrupted.predictions.place_probability)
    assert resumed.global_step == state.global_step == 2
