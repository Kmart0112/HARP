from dataclasses import replace

import numpy as np
import pytest

torch = pytest.importorskip('torch')

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import collate_nn_races
from harp.core.nn.losses import nn_odds_loss
from harp.core.nn.odds_targets import prepare_nn_odds_targets
from harp.core.nn.tensor_batch import NnInputSpec, NnModelInputs
from harp.core.nn.training import (
    evaluate_nn,
    initialize_nn_training,
    train_one_nn_epoch,
)
from tests.nn_odds_training_support import odds_recipe, odds_training_deps
from tests.nn_training_support import small_prepared, small_recipe


def test_log_midpoint_standardization_is_train_only_and_replay_uses_saved_moments():
    _, _, _, snapshot, reference = odds_training_deps()
    targets, state = prepare_nn_odds_targets(snapshot, reference)
    assert (state.mean, state.scale, state.training_entries) == pytest.approx((2., 1., 2))
    np.testing.assert_allclose(targets.odds_target, [-1., 1., 8., 8.])
    _, _, _, changed, _ = odds_training_deps(future_log_odds=5)
    other, fitted = prepare_nn_odds_targets(changed, reference)
    assert fitted == state
    replay, restored = prepare_nn_odds_targets(changed, reference, transform=state)
    assert restored == state
    np.testing.assert_array_equal(replay.odds_target, other.odds_target)
    bad = reference.copy()
    bad.loc[0, 'kettonum'] = 'other'
    with pytest.raises(NnInputContractError, match='entries or splits'):
        prepare_nn_odds_targets(snapshot, bad)


def test_missing_odds_preserve_main_labels_and_never_enter_features():
    deps, _, _, snapshot, reference = odds_training_deps(missing_train=True)
    prepared = small_prepared(deps.input_store.load('a' * 64).inputs)
    targets, transform = prepare_nn_odds_targets(snapshot, reference)
    attached = replace(prepared, dataset=prepared.dataset.with_odds_targets(targets.iloc[::-1], scale=transform.scale))
    original = collate_nn_races([prepared.split('train')[0]])
    actual = collate_nn_races([attached.split('train')[0]])
    for name in ('labels', 'label_mask', 'entrant_mask', 'finish_order'):
        np.testing.assert_array_equal(actual[name], original[name])
    assert actual['odds_mask'].tolist() == [[True, False]]
    assert actual['odds_target'].tolist() == [[0., 0.]]
    a, b = NnModelInputs.from_numpy(actual, 'cpu'), NnModelInputs.from_numpy(original, 'cpu')
    for name in vars(a):
        torch.testing.assert_close(getattr(a, name), getattr(b, name), rtol=0, atol=0)


def test_huber_averages_available_entrants_and_ignores_nan_padding_and_missing_targets():
    scores = torch.tensor([[0., 0., float('nan')], [0., float('nan'), float('nan')]], requires_grad=True)
    targets = torch.tensor([[.5, 2., float('nan')], [1., float('nan'), float('nan')]])
    entrants = torch.tensor([[True, True, True], [True, False, False]])
    mask = torch.tensor([[True, True, False], [True, False, False]])
    loss = nn_odds_loss(scores, targets, entrants, mask)
    assert loss.item() == pytest.approx((.125 + 1.5 + .5) / 3)
    loss.backward()
    assert torch.isfinite(scores.grad).all()
    assert (scores.grad[~mask] == 0).all()
    empty = nn_odds_loss(scores, targets, entrants, torch.zeros_like(mask))
    assert empty.item() == 0
    empty.backward()


def test_zero_weight_matches_no_head_with_dropout_and_positive_weight_learns():
    deps, _, _, snapshot, reference = odds_training_deps()
    prepared = small_prepared(deps.input_store.load('a' * 64).inputs)
    targets, transform = prepare_nn_odds_targets(snapshot, reference)
    prepared = replace(prepared, dataset=prepared.dataset.with_odds_targets(targets, scale=transform.scale))
    outputs = []
    for recipe in (small_recipe(**{'model.dropout': .2}), odds_recipe(0, **{'model.dropout': .2}), odds_recipe(.1, **{'model.dropout': .2})):
        state = initialize_nn_training(NnInputSpec.from_preprocessing(prepared.preprocessing), recipe, 'cpu')
        for _ in range(3):
            train_one_nn_epoch(state, prepared.split('train'), recipe, 'cpu')
        outputs.append(evaluate_nn(state.model, prepared.dataset, batch_size=2, device='cpu'))
    np.testing.assert_array_equal(outputs[0].predictions.place_probability, outputs[1].predictions.place_probability)
    assert not np.allclose(outputs[0].predictions.place_probability, outputs[2].predictions.place_probability)
    assert outputs[2].metrics['odds_entries'] == 4
