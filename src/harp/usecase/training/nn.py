"""NN training procedure; all external state is accessed through Ports."""
from dataclasses import asdict, replace

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import restore_nn_dataset
from harp.core.nn.odds_targets import (
    NnOddsTransform,
    prepare_nn_odds_targets,
    select_nn_odds_reference,
)
from harp.core.nn.tasks import nn_target
from harp.core.nn.tensor_batch import NnInputSpec
from harp.core.nn.training import (
    capture_nn_checkpoint,
    evaluate_nn,
    initialize_nn_training,
    restore_nn_checkpoint,
    train_one_nn_epoch,
    update_nn_selection,
)

from .nn_dto import (
    NnEvaluateRequest,
    NnEvaluateResult,
    NnTrainDeps,
    NnTrainRequest,
    NnTrainResult,
)


def _validate_resume(req, saved, odds_metadata):
    if saved.metadata["prepared_dataset_id"] != req.prepared_dataset_id:
        raise NnInputContractError("resume requires the identical prepared Dataset")
    if saved.metadata.get("odds_target") != odds_metadata:
        raise NnInputContractError("resume requires identical odds snapshot and transform")
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


def _attach_odds(prepared, source, recipe, dataset_id, snapshot_id, store, *, saved_metadata=None):
    if store is None:
        raise NnInputContractError("odds training/evaluation requires a snapshot store")
    snapshot = store.load(snapshot_id)
    if snapshot.prepared_dataset_id != dataset_id or snapshot.input_dataset_id != recipe.input_dataset_id:
        raise NnInputContractError("odds snapshot refers to a different Dataset")
    reference = select_nn_odds_reference(source.inputs.entries, prepared.partitions)
    transform = NnOddsTransform(**saved_metadata["transform"]) if saved_metadata else None
    targets, transform = prepare_nn_odds_targets(snapshot, reference, transform=transform)
    metadata = {"snapshot_id": snapshot_id, "transform": asdict(transform), "entry_keys_sha256": snapshot.entry_keys_sha256}
    if saved_metadata is not None and metadata != saved_metadata:
        raise NnInputContractError("saved odds target contract differs from snapshot")
    return replace(prepared, dataset=prepared.dataset.with_odds_targets(targets, scale=transform.scale)), metadata


def run_nn_train_usecase(req: NnTrainRequest, deps: NnTrainDeps) -> NnTrainResult:
    recipe = deps.prepared_store.load(req.prepared_dataset_id)
    if recipe.config.task != req.recipe.task:
        raise NnInputContractError("NN Dataset task differs from training task")
    source = deps.input_store.load(recipe.input_dataset_id).inputs
    prepared = restore_nn_dataset(source, recipe.config, recipe.preprocessing, recipe.partitions)
    if req.recipe.auxiliary_odds is not None and req.odds_snapshot_id is None:
        raise NnInputContractError("odds head requires an immutable odds snapshot")
    odds_metadata = None
    if req.odds_snapshot_id is not None:
        prepared, odds_metadata = _attach_odds(prepared, source, recipe, req.prepared_dataset_id,
                                               req.odds_snapshot_id, deps.odds_store)
    train, validation = prepared.split("train"), prepared.split("validation")
    if not len(train) or not len(validation):
        raise NnInputContractError("NN training requires nonempty train and validation splits")
    saved = deps.model_store.load_checkpoint(req.resume_run_id) if req.resume_run_id else None
    if saved is not None:
        _validate_resume(req, saved, odds_metadata)
    spec = NnInputSpec.from_preprocessing(prepared.preprocessing)
    state = initialize_nn_training(spec, req.recipe, req.device)
    if saved is not None:
        restore_nn_checkpoint(state, saved.checkpoint, req.device)
    metadata = {
        "version": 1, "task": req.recipe.task, "target": nn_target(req.recipe.task), "prepared_dataset_id": req.prepared_dataset_id,
        "input_dataset_id": recipe.input_dataset_id, "recipe": asdict(req.recipe),
        "preprocessing": asdict(prepared.preprocessing), "input_spec": asdict(spec),
        "history_length": prepared.config.history_length, "dataset_config": asdict(prepared.config),
        "split_summary": prepared.summary, "device": req.device, "provenance": req.provenance,
        "input_contract": asdict(source.inputs.contract), "input_query": asdict(source.inputs.query),
        "source_revision": source.inputs.source_revision, "captured_at": source.inputs.captured_at.isoformat(),
        "parent_run_id": req.resume_run_id,
        "parent_checkpoint_id": saved.checkpoint_id if saved is not None else None,
        "odds_target": odds_metadata,
    }
    run_id = deps.model_store.create_run(metadata)
    tracking_id = None
    try:
        if deps.tracking is not None and req.tracking_experiment is not None:
            tracking_id = deps.tracking.start_run(req.tracking_experiment, f"nn_{run_id}",
                                                  tags={"model": req.recipe.model.name, "task": req.recipe.task})
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
                            state.best_epoch, state.best_logloss, stopped, prepared.summary, tracking_id, task=req.recipe.task)
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
            or recipe.config.history_length != saved.metadata["history_length"]
            or recipe.config.task != saved.recipe.task):
        raise NnInputContractError("evaluation Dataset differs from the trained model contract")
    source = deps.input_store.load(recipe.input_dataset_id).inputs
    prepared = restore_nn_dataset(source, recipe.config, recipe.preprocessing, recipe.partitions)
    odds_metadata = saved.metadata.get("odds_target")
    if saved.recipe.auxiliary_odds is not None and odds_metadata is None:
        raise NnInputContractError("saved odds head is missing its target contract")
    if odds_metadata is not None:
        prepared, _ = _attach_odds(prepared, source, recipe, dataset_id, odds_metadata["snapshot_id"],
                                    deps.odds_store, saved_metadata=odds_metadata)
    predictor = NnPredictor.from_weights(saved.preprocessing, saved.recipe.model,
                                         saved.checkpoint["best_weights"], recipe.config.history_length, req.device, task=saved.recipe.task,
                                         auxiliary_rank=saved.recipe.auxiliary_rank, auxiliary_odds=saved.recipe.auxiliary_odds)
    evaluation = evaluate_nn(predictor.model, prepared.split(req.split), batch_size=req.batch_size, device=req.device)
    return NnEvaluateResult(req.run_id, saved.checkpoint_id, dataset_id, req.split,
                            saved.checkpoint["best_epoch"], evaluation.metrics, task=saved.recipe.task)
