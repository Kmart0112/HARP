from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('torch')

from harp.core.nn.contracts import NnInputContractError
from harp.usecase.prediction.nn import load_nn_predictor
from harp.usecase.training.nn import run_nn_evaluate_usecase, run_nn_train_usecase
from harp.usecase.training.nn_dto import NnEvaluateRequest, NnTrainRequest
from tests.nn_odds_training_support import odds_recipe, odds_training_deps


def request(recipe, **kwargs):
    return NnTrainRequest('b' * 64, recipe, 'cpu', {'source': 'fixture'}, odds_snapshot_id='c' * 64, **kwargs)


def test_future_odds_cannot_change_training_or_selection_and_evaluation_reuses_transform():
    results = []
    for future in (4., 10.):
        deps, _, _, _, _ = odds_training_deps(future_log_odds=future, missing_train=True)
        result = run_nn_train_usecase(request(odds_recipe()), deps)
        saved = deps.model_store.load_checkpoint(result.run_id)
        history = saved.checkpoint['metrics_history']
        assert result.best_validation_logloss == min(row['validation']['logloss'] for row in history)
        assert all(row['train']['odds_entries'] == 1 and row['train']['entries'] == 2 for row in history)
        predictor = load_nn_predictor(result.run_id, deps.model_store)
        predictions = predictor.predict(deps.input_store.load('a' * 64).inputs.inputs)
        evaluation = run_nn_evaluate_usecase(NnEvaluateRequest(result.run_id, 'cpu'), deps)
        assert evaluation.metrics['odds_entries'] == 1
        results.append((result.best_validation_logloss, predictions, saved.metadata['odds_target']['transform'], evaluation))
    assert results[0][0] == results[1][0]
    np.testing.assert_array_equal(results[0][1].place_probability, results[1][1].place_probability)
    assert results[0][2] == results[1][2]
    assert results[0][3].metrics['odds_log_mae'] != results[1][3].metrics['odds_log_mae']


def test_odds_resume_matches_uninterrupted_and_rejects_different_teacher_before_writing():
    deps, runs, _, _, _ = odds_training_deps()
    recipe = odds_recipe(**{'training.max_epochs': 1, 'model.dropout': .2})
    first = run_nn_train_usecase(request(recipe), deps)
    extended = replace(recipe, training=replace(recipe.training, max_epochs=3))
    resumed = run_nn_train_usecase(request(extended, resume_run_id=first.run_id), deps)
    full = run_nn_train_usecase(request(extended), deps)
    source = deps.input_store.load('a' * 64).inputs.inputs
    np.testing.assert_array_equal(load_nn_predictor(resumed.run_id, deps.model_store).predict(source).place_probability,
                                  load_nn_predictor(full.run_id, deps.model_store).predict(source).place_probability)
    with pytest.raises(NnInputContractError, match='resume'):
        run_nn_train_usecase(replace(request(extended, resume_run_id=first.run_id), odds_snapshot_id='d' * 64), deps)
    assert len(runs) == 3


@pytest.mark.parametrize('change', ['missing_snapshot', 'wrong_dataset'])
def test_odds_training_rejects_missing_or_wrong_teacher_before_run_publication(change):
    deps, runs, _, _, _ = odds_training_deps()
    req = request(odds_recipe())
    req = replace(req, odds_snapshot_id=None) if change == 'missing_snapshot' else replace(req, prepared_dataset_id='d' * 64)
    with pytest.raises(NnInputContractError):
        run_nn_train_usecase(req, deps)
    assert not runs
