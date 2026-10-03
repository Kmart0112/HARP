from dataclasses import replace

import pytest
pytest.importorskip("torch")

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.split import NnDatasetConfig
from harp.usecase.training.nn import run_nn_evaluate_usecase, run_nn_train_usecase
from harp.usecase.training.nn_dto import NnEvaluateRequest, NnTrainRequest
from tests.nn_dataset_support import dataset_inputs, replace_inputs, win_dataset_inputs
from tests.nn_training_support import nn_architecture, small_recipe, training_deps, torch_cpu_runtime


def request(recipe=None, **kwargs):
    return NnTrainRequest("b" * 64, recipe or small_recipe(), "cpu", {"source": "test"}, tracking_experiment="fixture", **kwargs)


def test_training_publishes_best_and_last_state_and_tracks_validation_without_testing_holdout(nn_architecture):
    deps, runs, tracking = training_deps()
    result = run_nn_train_usecase(request(small_recipe(**{"model.name": nn_architecture})), deps)
    snapshot = runs[result.run_id]["checkpoints"][result.checkpoint_id]
    assert runs[result.run_id]["metadata"]["recipe"]["model"]["name"] == nn_architecture
    assert result.completed_epochs == 3
    assert 1 <= result.best_epoch <= result.completed_epochs
    assert snapshot["best_epoch"] == result.best_epoch
    assert snapshot["best_logloss"] == result.best_validation_logloss
    assert tracking["status"] == "FINISHED"
    assert [step for step, _ in tracking["metrics"]] == [1, 2, 3]
    assert all(not key.startswith("test.") for _, metrics in tracking["metrics"] for key in metrics)
    assert result.split_summary["test"]["races"] == 1


def test_test_labels_do_not_change_selected_model_or_validation_metrics():
    source = dataset_inputs(future_rate=.4)
    changed = source.targets
    changed.loc[changed.race_id == "R4", "is_place"] = False
    outputs = []
    for inputs in (source, replace_inputs(source, targets=changed)):
        deps, _, _ = training_deps(inputs)
        outputs.append(run_nn_train_usecase(request(), deps))
    assert outputs[0].best_epoch == outputs[1].best_epoch
    assert outputs[0].best_validation_logloss == outputs[1].best_validation_logloss


def test_explicit_test_evaluation_uses_saved_best_model_without_another_training_run():
    deps, runs, _ = training_deps()
    trained = run_nn_train_usecase(request(), deps)
    result = run_nn_evaluate_usecase(NnEvaluateRequest(trained.run_id, "cpu"), deps)
    assert result.split == "test"
    assert result.metrics["races"] == 1
    assert result.metrics["entries"] == 1
    assert result.best_epoch == trained.best_epoch
    assert result.checkpoint_id == trained.checkpoint_id
    assert len(runs) == 1


def test_early_stopping_and_resume_keep_the_epoch_boundary_contract(nn_architecture):
    deps, runs, _ = training_deps()
    recipe = small_recipe(**{"model.name": nn_architecture, "training.max_epochs": 1, "model.dropout": .2})
    first = run_nn_train_usecase(request(recipe), deps)
    extended = replace(recipe, training=replace(recipe.training, max_epochs=3))
    result = run_nn_train_usecase(request(extended, resume_run_id=first.run_id), deps)
    assert result.completed_epochs == 3
    assert runs[result.run_id]["metadata"]["parent_run_id"] == first.run_id
    assert len(runs[result.run_id]["checkpoints"]) == 2
    stop_recipe = small_recipe(**{"model.name": nn_architecture, "training.max_epochs": 10,
                                 "early_stopping.min_delta": 100, "early_stopping.patience": 2})
    stopped = run_nn_train_usecase(request(stop_recipe), deps)
    assert stopped.stopped_early
    assert stopped.completed_epochs == 3


@pytest.mark.parametrize("mismatch", ["dataset", "recipe", "architecture", "provenance"])
def test_resume_rejects_mismatched_experiment_before_creating_another_run(mismatch):
    deps, runs, _ = training_deps()
    initial_recipe = small_recipe(**{"training.max_epochs": 1})
    initial = run_nn_train_usecase(request(initial_recipe), deps)
    req = request(resume_run_id=initial.run_id)
    if mismatch == "dataset":
        req = replace(req, prepared_dataset_id="c" * 64)
    elif mismatch == "recipe":
        req = replace(req, recipe=small_recipe(**{"optimizer.lr": .01}))
    elif mismatch == "architecture":
        req = replace(req, recipe=small_recipe(**{"model.name": "history_conditioned_set_transformer_v1"}))
    else:
        req = replace(req, provenance={"source": "changed"})
    with pytest.raises(NnInputContractError, match="resume"):
        run_nn_train_usecase(req, deps)
    assert len(runs) == 1


def test_empty_validation_split_does_not_publish_a_training_run():
    deps, runs, _ = training_deps(config=NnDatasetConfig("2026-06-21", "2026-06-22", 3))
    with pytest.raises(NnInputContractError, match="nonempty train and validation"):
        run_nn_train_usecase(request(), deps)
    assert not runs


def test_failed_checkpoint_publication_leaves_last_completed_epoch_and_failed_tracking_status():
    deps, runs, tracking = training_deps()
    save = deps.model_store.save_checkpoint.side_effect

    def fail_second_epoch(run_id, checkpoint):
        if checkpoint["epoch"] == 2:
            raise OSError("disk full")
        return save(run_id, checkpoint)

    deps.model_store.save_checkpoint.side_effect = fail_second_epoch
    with pytest.raises(OSError, match="disk full"):
        run_nn_train_usecase(request(), deps)
    assert tracking["status"] == "FAILED"
    run = next(iter(runs.values()))
    assert [state["epoch"] for state in run["checkpoints"].values()] == [1]


def test_win_training_is_selected_only_on_validation_and_can_resume_and_evaluate():
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3, task="win")
    recipe = small_recipe(task="win", **{"loss.name": "cross_entropy", "loss.reduction": "race_mean",
                                         "training.max_epochs": 1})
    source = win_dataset_inputs()
    changed = source.targets
    test = changed.race_id.eq("R4")
    changed.loc[test, "is_win"] = ~changed.loc[test, "is_win"]
    changed.loc[test, "result_order"] = changed.loc[test, "is_win"].map({True: 1, False: 2})
    initial = []
    for inputs in (source, replace_inputs(source, targets=changed)):
        deps, runs, _ = training_deps(inputs, config)
        initial.append(run_nn_train_usecase(request(recipe), deps))
    assert initial[0].best_validation_logloss == initial[1].best_validation_logloss
    extended = replace(recipe, training=replace(recipe.training, max_epochs=3))
    trained = run_nn_train_usecase(request(extended, resume_run_id=initial[-1].run_id), deps)
    assert trained.completed_epochs == 3
    assert runs[trained.run_id]["metadata"]["target"] == "is_win"
    evaluation = run_nn_evaluate_usecase(NnEvaluateRequest(trained.run_id, "cpu"), deps)
    assert evaluation.metrics["labelled_races"] == 1
    assert evaluation.metrics["labelled_entries"] == 2
    assert 0 <= evaluation.metrics["top1_accuracy"] <= 1


@pytest.mark.parametrize("dataset_task", ["place", "win"])
def test_mismatched_dataset_and_training_task_does_not_publish_a_model(dataset_task):
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3, task=dataset_task)
    deps, runs, _ = training_deps(win_dataset_inputs(), config)
    recipe = small_recipe() if dataset_task == "win" else small_recipe(
        task="win", **{"loss.name": "cross_entropy", "loss.reduction": "race_mean"})
    with pytest.raises(NnInputContractError, match="task"):
        run_nn_train_usecase(request(recipe), deps)
    assert not runs
