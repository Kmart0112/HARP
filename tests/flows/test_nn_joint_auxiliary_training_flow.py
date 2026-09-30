from dataclasses import replace

import numpy as np
import pytest

torch = pytest.importorskip('torch')

from harp.core.nn.config import NnAuxiliaryRankConfig
from harp.usecase.prediction.nn import load_nn_predictor
from harp.usecase.training.nn import run_nn_train_usecase
from harp.usecase.training.nn_dto import NnTrainRequest
from tests.nn_odds_training_support import odds_recipe, odds_training_deps


def test_joint_training_keeps_both_objectives_and_zero_weights_preserve_main_training():
    original_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        deps, _, _, _, _ = odds_training_deps(missing_train=True)
        source = deps.input_store.load('a' * 64).inputs.inputs
        base = odds_recipe(**{'model.dropout': .2})
        recipes = [replace(base, auxiliary_odds=None)]
        for rank_weight, odds_weight in ((0., 0.), (.3, 0.), (0., .1), (.3, .1)):
            recipes.append(replace(base,
                auxiliary_rank=NnAuxiliaryRankConfig('pairwise_logistic', rank_weight, 'race_mean', 'ignore'),
                auxiliary_odds=replace(base.auxiliary_odds, weight=odds_weight)))
        predictions = []
        for recipe in recipes:
            result = run_nn_train_usecase(NnTrainRequest('b' * 64, recipe, 'cpu', {'source': 'joint-fixture'},
                                                       odds_snapshot_id='c' * 64), deps)
            saved = deps.model_store.load_checkpoint(result.run_id)
            history = saved.checkpoint['metrics_history']
            assert result.best_validation_logloss == min(row['validation']['logloss'] for row in history)
            if recipe.auxiliary_rank is not None:
                for row in history:
                    train = row['train']
                    assert train['rank_pairs'] == 1
                    assert train['odds_entries'] == 1 and train['entries'] == 2
                    assert train['total_loss'] == pytest.approx(train['logloss']
                        + recipe.auxiliary_rank.weight * train['rank_loss']
                        + recipe.auxiliary_odds.weight * train['odds_huber'], abs=1e-12)
            # Public restore predicts from features alone, even with both heads.
            predictions.append(load_nn_predictor(result.run_id, deps.model_store).predict(source).place_probability)
        np.testing.assert_array_equal(predictions[0], predictions[1])
        # Both objectives affect the final predictor; neither overwrites the other.
        assert not np.allclose(predictions[4], predictions[2], rtol=1e-6, atol=1e-7)
        assert not np.allclose(predictions[4], predictions[3], rtol=1e-6, atol=1e-7)
    finally:
        torch.set_num_threads(original_threads)
