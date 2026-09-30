import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import NnRaceDataset, collate_nn_races
from harp.core.nn.losses import nn_rank_objective
from harp.core.nn.tensor_batch import NnInputSpec, NnModelInputs
from harp.core.nn.training import evaluate_nn, initialize_nn_training, train_one_nn_epoch
from tests.nn_dataset_support import replace_inputs, win_dataset_inputs
from tests.nn_training_support import rank_recipe, small_prepared, small_recipe, torch_cpu_runtime


def test_rank_objective_uses_each_strict_pair_once_and_weights_fields_equally():
    scores = torch.tensor([[2., 0., float("nan")], [0., 0., 0.]], requires_grad=True)
    orders = torch.tensor([[1., 2., float("nan")], [1., 2., 3.]])
    valid = torch.tensor([[True, True, False], [True, True, True]])
    result = nn_rank_objective(scores, orders, valid, valid)
    assert result.pair_counts.tolist() == [1, 3]
    assert result.loss.item() == pytest.approx((math.log1p(math.exp(-2)) + math.log(2)) / 2)
    assert result.race_accuracy.tolist() == [1., .5]
    result.loss.backward()
    assert torch.isfinite(scores.grad).all()
    assert scores.grad[0, 0] < 0 < scores.grad[0, 1]
    assert scores.grad[0, 2] == 0


def test_rank_ties_missing_orders_and_padding_never_create_artificial_preferences():
    scores = torch.tensor([[1., 1., 0., float("nan")]], requires_grad=True)
    orders = torch.tensor([[1, 1, 3, 0]])
    entrants = torch.ones(1, 4, dtype=torch.bool)
    known = torch.tensor([[True, True, True, False]])
    result = nn_rank_objective(scores, orders, entrants, known)
    assert result.pair_counts.item() == 2
    assert result.loss.item() == pytest.approx(math.log1p(math.exp(-1)))
    assert result.race_accuracy.item() == 1
    result.loss.backward()
    assert scores.grad[0, 3] == 0


@pytest.mark.parametrize("orders,known", [([1, 1], [True, True]), ([1, 0], [True, False]), ([0, 0], [False, False])])
def test_no_comparable_pairs_give_zero_loss_and_zero_gradient(orders, known):
    scores = torch.tensor([[1., -1.]], requires_grad=True)
    result = nn_rank_objective(scores, torch.tensor([orders]), torch.ones(1, 2, dtype=torch.bool), torch.tensor([known]))
    assert result.loss.item() == 0
    assert result.pair_counts.item() == 0
    result.loss.backward()
    torch.testing.assert_close(scores.grad, torch.zeros_like(scores))


@pytest.mark.parametrize("orders", [[0., 2.], [1.5, 2.], [float("nan"), 2.]])
def test_invalid_known_finishing_positions_are_rejected(orders):
    with pytest.raises(NnInputContractError, match="finishing positions"):
        nn_rank_objective(torch.zeros(1, 2), torch.tensor([orders]),
                          torch.ones(1, 2, dtype=torch.bool), torch.ones(1, 2, dtype=torch.bool))


def test_order_targets_align_with_entries_but_never_enter_model_features():
    source = win_dataset_inputs()
    targets = source.targets
    targets.loc[targets.race_id.eq("R2"), "result_order"] = [2, 1]
    prepared = small_prepared(replace_inputs(source, targets=targets.iloc[::-1]))
    batch = collate_nn_races([prepared.split("train")[0]])
    assert batch["finish_order"].tolist() == [[2, 1]]
    assert "finish_order" not in vars(NnModelInputs.from_numpy(batch, "cpu"))
    inference = NnRaceDataset(source.inputs, prepared.preprocessing, 3)
    assert not collate_nn_races([inference[0]])["finish_order_mask"].any()


def test_zero_auxiliary_weight_preserves_main_training_with_dropout():
    prepared = small_prepared()
    recipes = (small_recipe(**{"model.dropout": .2}), rank_recipe(0, **{"model.dropout": .2}))
    results = []
    for recipe in recipes:
        state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, "cpu")
        for _ in range(2):
            metrics = train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
        results.append((metrics, evaluate_nn(state.model, prepared.dataset, batch_size=2, device="cpu")))
    assert results[0][0]["logloss"] == results[1][0]["logloss"]
    assert results[1][0]["total_loss"] == results[1][0]["logloss"]
    np.testing.assert_array_equal(results[0][1].predictions.place_probability, results[1][1].predictions.place_probability)


def test_auxiliary_ranking_learns_and_evaluation_is_batch_and_permutation_invariant():
    source = win_dataset_inputs()
    prepared = small_prepared(source)
    recipe = rank_recipe(.3)
    state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, "cpu")
    before = evaluate_nn(state.model, prepared.split("train"), batch_size=1, device="cpu")
    for _ in range(12):
        train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
    after = evaluate_nn(state.model, prepared.split("train"), batch_size=1, device="cpu")
    assert after.metrics["rank_loss"] < before.metrics["rank_loss"]
    assert after.metrics["logloss"] < before.metrics["logloss"]
    one = evaluate_nn(state.model, prepared.dataset, batch_size=1, device="cpu")
    many = evaluate_nn(state.model, prepared.dataset, batch_size=3, device="cpu")
    for metric in ("logloss", "rank_loss", "rank_pair_accuracy", "rank_pairs", "rank_races"):
        assert one.metrics[metric] == pytest.approx(many.metrics[metric], abs=1e-6)
    batch = collate_nn_races([prepared.split("train")[0]])
    output = state.model.forward_outputs(NnModelInputs.from_numpy(batch, "cpu"))
    permuted = {name: value[:, ::-1].copy() if isinstance(value, np.ndarray) else value for name, value in batch.items()}
    reordered = state.model.forward_outputs(NnModelInputs.from_numpy(permuted, "cpu"))
    torch.testing.assert_close(output.logits.flip(1), reordered.logits)
    torch.testing.assert_close(output.rank_scores.flip(1), reordered.rank_scores)


def test_train_ranks_affect_place_predictions_with_identical_primary_labels():
    source = win_dataset_inputs()
    changed = source.targets
    changed.loc[changed.race_id.eq("R2"), "result_order"] = [2, 1]
    predictions = []
    for inputs in (source, replace_inputs(source, targets=changed)):
        prepared = small_prepared(inputs)
        recipe = rank_recipe(.3)
        state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, "cpu")
        train_one_nn_epoch(state, prepared.split("train"), recipe, "cpu")
        predictions.append(evaluate_nn(state.model, prepared.split("validation"), batch_size=1, device="cpu").predictions.place_probability)
    assert not np.allclose(predictions[0], predictions[1], rtol=1e-5, atol=1e-6)
