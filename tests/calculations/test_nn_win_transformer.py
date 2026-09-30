from dataclasses import replace
import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from harp.core.calibration_prediction import evaluate_calibration
from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import prepare_nn_dataset
from harp.core.nn.losses import nn_probabilities, nn_win_loss
from harp.core.nn.prediction import NnPredictor
from harp.core.nn.split import NnDatasetConfig
from harp.core.nn.tensor_batch import NnInputSpec
from harp.core.nn.training import evaluate_nn, initialize_nn_training, train_one_nn_epoch
from tests.nn_dataset_support import win_dataset_inputs
from tests.nn_training_support import small_recipe, torch_cpu_runtime


def test_win_loss_weights_races_equally_and_ignores_padded_logits_and_labels():
    logits = torch.tensor([[0., 0., float("nan")], [0., 0., 0.]], requires_grad=True)
    mask = torch.tensor([[True, True, False], [True, True, True]])
    labels = torch.tensor([[0., 1., float("nan")], [1., 0., 0.]])
    loss = nn_win_loss(logits, labels, mask, mask)
    assert loss.item() == pytest.approx((math.log(2) + math.log(3)) / 2)
    probability = nn_probabilities(logits, mask, "win")
    torch.testing.assert_close(probability.sum(dim=1), torch.ones(2))
    assert probability[0, 2] == 0
    loss.backward()
    assert torch.isfinite(logits.grad).all()
    assert logits.grad[0, 2] == 0


@pytest.mark.parametrize("labels,known", [([1., 1.], [True, True]), ([0., 0.], [True, True]),
                                             ([1., 0.], [True, False])])
def test_win_loss_rejects_ties_missing_winner_and_partial_labels(labels, known):
    with pytest.raises(NnInputContractError):
        nn_win_loss(torch.zeros(1, 2), torch.tensor([labels]), torch.ones(1, 2, dtype=torch.bool),
                    torch.tensor([known]))


def test_win_model_learns_and_predicts_normalized_probabilities_after_restoring_weights():
    source = win_dataset_inputs()
    prepared = prepare_nn_dataset(source, NnDatasetConfig("2026-06-13", "2026-06-20", 3, task="win"))
    recipe = small_recipe(task="win", **{"loss.name": "cross_entropy", "loss.reduction": "race_mean"})
    state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, "cpu")
    before = evaluate_nn(state.model, prepared.split("train"), batch_size=1, device="cpu")
    for _ in range(10):
        train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
    after = evaluate_nn(state.model, prepared.split("train"), batch_size=1, device="cpu")
    assert after.metrics["logloss"] < before.metrics["logloss"] * .5
    assert after.metrics["top1_accuracy"] == 1
    one = evaluate_nn(state.model, prepared.dataset, batch_size=1, device="cpu")
    many = evaluate_nn(state.model, prepared.dataset, batch_size=3, device="cpu")
    for name in ("logloss", "brier", "race_brier", "top1_accuracy"):
        assert one.metrics[name] == pytest.approx(many.metrics[name], abs=1e-6)
    predictor = NnPredictor.from_weights(prepared.preprocessing, recipe.model, state.model.state_dict(), 3, "cpu", task="win")
    actual = predictor.predict(source.inputs)
    np.testing.assert_allclose(actual.win_probability, many.predictions.win_probability, atol=1e-6)
    np.testing.assert_allclose(actual.groupby("race_id").win_probability.sum(), 1, atol=1e-6)
    report = evaluate_calibration(predictor, prepared, split="all")
    assert report.metrics["observed_rate"] == .5
    assert report.metadata["target"] == "is_win"
    with pytest.raises(ValueError, match="contract"):
        evaluate_calibration(replace(predictor, task="place"), prepared)
