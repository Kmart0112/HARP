"""NN training procedure; all external state is accessed through Ports."""
from dataclasses import asdict

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import restore_nn_dataset
from harp.core.nn.tensor_batch import NnInputSpec
from harp.core.nn.training import (
    capture_nn_checkpoint, evaluate_nn, initialize_nn_training,
    restore_nn_checkpoint, train_one_nn_epoch, update_nn_selection,
)
from .nn_dto import NnEvaluateRequest, NnEvaluateResult, NnTrainDeps, NnTrainRequest, NnTrainResult


def _validate_resume(req, saved):
    if saved.metadata["prepared_dataset_id"] != req.prepared_dataset_id:
        raise NnInputContractError("resume requires the identical prepared Dataset")
    previous, current = asdict(saved.recipe), asdict(req.recipe)
    previous["training"].pop("max_epochs")
    current["training"].pop("max_epochs")
    if previous != current:
        raise NnInputContractError("resume may only change training.max_epochs")
    if saved.metadata["device"] != req.device or saved.metadata["provenance"] != req.provenance:
        raise NnInputContractError("resume requires the same code and runtime provenance")
    if req.recipe.training.max_epochs <= saved.checkpoint["epoch"]:
        raise NnInputContractError("resume max_epochs must exceed the completed epoch")
    if saved.checkpoint["bad_epochs"] >= req.recipe.early_stopping.patience:
        raise NnInputContractError("cannot resume a run that already early-stopped")


def run_nn_train_usecase(req: NnTrainRequest, deps: NnTrainDeps) -> NnTrainResult:
    recipe = deps.prepared_store.load(req.prepared_dataset_id)
    source = deps.input_store.load(recipe.input_dataset_id).inputs
    prepared = restore_nn_dataset(source, recipe.config, recipe.preprocessing, recipe.partitions)
    train, validation = prepared.split("train"), prepared.split("validation")
    if not len(train) or not len(validation):
        raise NnInputContractError("NN training requires nonempty train and validation splits")
    saved = deps.model_store.load_checkpoint(req.resume_run_id) if req.resume_run_id else None
    if saved is not None:
        _validate_resume(req, saved)
    spec = NnInputSpec.from_preprocessing(prepared.preprocessing)
    state = initialize_nn_training(spec, req.recipe, req.device)
    if saved is not None:
        restore_nn_checkpoint(state, saved.checkpoint, req.device)
    metadata = {
        "version": 1, "target": "is_place", "prepared_dataset_id": req.prepared_dataset_id,
        "input_dataset_id": recipe.input_dataset_id, "recipe": asdict(req.recipe),
        "preprocessing": asdict(prepared.preprocessing), "input_spec": asdict(spec),
        "history_length": prepared.config.history_length, "dataset_config": asdict(prepared.config),
        "split_summary": prepared.summary, "device": req.device, "provenance": req.provenance,
        "input_contract": asdict(source.inputs.contract), "input_query": asdict(source.inputs.query),
        "source_revision": source.inputs.source_revision, "captured_at": source.inputs.captured_at.isoformat(),
        "parent_run_id": req.resume_run_id,
        "parent_checkpoint_id": saved.checkpoint_id if saved is not None else None,
    }
    run_id = deps.model_store.create_run(metadata)
    tracking_id = None
    try:
        if deps.tracking is not None and req.tracking_experiment is not None:
            tracking_id = deps.tracking.start_run(req.tracking_experiment, f"nn_{run_id}", tags={"model": req.recipe.model.name})
            deps.tracking.log_dict(tracking_id, metadata, "resolved_training.json")
            deps.tracking.log_params(tracking_id, {"prepared_dataset_id": req.prepared_dataset_id, "seed": req.recipe.training.seed,
                                                    "learning_rate": req.recipe.optimizer.lr, "device": req.device})
        stopped, checkpoint_id = False, None
        while state.epoch < req.recipe.training.max_epochs:
            learning_rate = state.optimizer.param_groups[0]["lr"]
            train_metrics = train_one_nn_epoch(state, train, req.recipe, req.device)
            evaluation = evaluate_nn(state.model, validation, batch_size=req.recipe.training.batch_size_races,
                                     device=req.device, num_workers=req.recipe.runtime.num_workers)
            stopped = update_nn_selection(state, evaluation, req.recipe)
            record = {"epoch": state.epoch, "learning_rate": learning_rate, "train": train_metrics, "validation": evaluation.metrics}
            state.metrics_history.append(record)
            checkpoint_id = deps.model_store.save_checkpoint(run_id, capture_nn_checkpoint(state, req.device))
            if tracking_id is not None:
                metrics = {f"{split}.{name}": float(value) for split, values in (("train", train_metrics), ("validation", evaluation.metrics))
                           for name, value in values.items() if value is not None}
                deps.tracking.log_metrics(tracking_id, metrics | {"learning_rate": learning_rate}, step=state.epoch)
                deps.tracking.log_dict(tracking_id, {"run_id": run_id, "checkpoint_id": checkpoint_id}, "latest_checkpoint.json")
            if stopped:
                break
        if tracking_id is not None:
            artifact = deps.model_store.load_checkpoint(run_id, checkpoint_id)
            deps.tracking.log_artifacts(tracking_id, artifact.artifact_path, artifact_path="model")
            deps.tracking.set_terminated(tracking_id, status="FINISHED")
        return NnTrainResult(run_id, checkpoint_id, req.prepared_dataset_id, state.epoch,
                            state.best_epoch, state.best_logloss, stopped, prepared.summary, tracking_id)
    except Exception:
        if tracking_id is not None:
            deps.tracking.set_terminated(tracking_id, status="FAILED")
        raise


def run_nn_evaluate_usecase(req: NnEvaluateRequest, deps: NnTrainDeps) -> NnEvaluateResult:
    """Explicit held-out evaluation; never called by training/selection."""
    from harp.core.nn.prediction import NnPredictor

    saved = deps.model_store.load_checkpoint(req.run_id, req.checkpoint_id)
    dataset_id = saved.metadata["prepared_dataset_id"]
    recipe = deps.prepared_store.load(dataset_id)
    if (recipe.input_dataset_id != saved.metadata["input_dataset_id"] or recipe.preprocessing != saved.preprocessing
            or recipe.config.history_length != saved.metadata["history_length"]):
        raise NnInputContractError("evaluation Dataset differs from the trained model contract")
    source = deps.input_store.load(recipe.input_dataset_id).inputs
    prepared = restore_nn_dataset(source, recipe.config, recipe.preprocessing, recipe.partitions)
    predictor = NnPredictor.from_weights(saved.preprocessing, saved.recipe.model,
                                         saved.checkpoint["best_weights"], recipe.config.history_length, req.device)
    evaluation = evaluate_nn(predictor.model, prepared.split(req.split), batch_size=req.batch_size, device=req.device)
    return NnEvaluateResult(req.run_id, saved.checkpoint_id, dataset_id, req.split,
                            saved.checkpoint["best_epoch"], evaluation.metrics)
