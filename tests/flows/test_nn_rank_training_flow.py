from dataclasses import replace

import numpy as np
import pytest
pytest.importorskip("torch")

from harp.core.nn.contracts import NnInputContractError
from harp.usecase.prediction.nn import load_nn_predictor
from harp.usecase.training.nn import run_nn_evaluate_usecase, run_nn_train_usecase
from harp.usecase.training.nn_dto import NnEvaluateRequest, NnTrainRequest
from tests.nn_dataset_support import replace_inputs, win_dataset_inputs
from tests.nn_training_support import rank_recipe, training_deps, torch_cpu_runtime


def request(recipe, **kwargs):
    return NnTrainRequest("b" * 64, recipe, "cpu", {"source": "rank-test"}, tracking_experiment="fixture", **kwargs)


def test_rank_training_selects_on_place_logloss_and_test_ranks_do_not_influence_it():
    source = win_dataset_inputs()
    changed = source.targets
    test = changed.race_id.eq("R4")
    changed.loc[test, "result_order"] = [2, 1]
    outputs = []
    for inputs in (source, replace_inputs(source, targets=changed)):
        deps, runs, tracking = training_deps(inputs)
        result = run_nn_train_usecase(request(rank_recipe()), deps)
        checkpoint = runs[result.run_id]["checkpoints"][result.checkpoint_id]
        history = checkpoint["metrics_history"]
        assert result.best_validation_logloss == min(row["validation"]["logloss"] for row in history)
        assert all("rank_loss" in row["validation"] and "total_loss" in row["train"] for row in history)
        assert all(not name.startswith("test.") for _, values in tracking["metrics"] for name in values)
        outputs.append((result, load_nn_predictor(result.run_id, deps.model_store).predict(source.inputs)))
    assert outputs[0][0].best_validation_logloss == outputs[1][0].best_validation_logloss
    np.testing.assert_array_equal(outputs[0][1].place_probability, outputs[1][1].place_probability)
    evaluated = run_nn_evaluate_usecase(NnEvaluateRequest(result.run_id, "cpu"), deps)
    assert evaluated.metrics["rank_pairs"] == 1


def test_auxiliary_checkpoint_resumes_with_dropout_and_rejects_changed_weight():
    source = win_dataset_inputs()
    deps, runs, _ = training_deps(source)
    recipe = rank_recipe(.1, **{"model.dropout": .2, "training.max_epochs": 1})
    first = run_nn_train_usecase(request(recipe), deps)
    extended = replace(recipe, training=replace(recipe.training, max_epochs=3))
    resumed = run_nn_train_usecase(request(extended, resume_run_id=first.run_id), deps)
    uninterrupted = run_nn_train_usecase(request(extended), deps)
    a = load_nn_predictor(resumed.run_id, deps.model_store).predict(source.inputs)
    b = load_nn_predictor(uninterrupted.run_id, deps.model_store).predict(source.inputs)
    np.testing.assert_array_equal(a.place_probability, b.place_probability)
    mismatch = replace(extended, auxiliary_rank=replace(recipe.auxiliary_rank, weight=.2))
    with pytest.raises(NnInputContractError, match="resume"):
        run_nn_train_usecase(request(mismatch, resume_run_id=first.run_id), deps)
    assert len(runs) == 3
