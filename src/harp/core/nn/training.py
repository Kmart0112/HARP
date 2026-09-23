"""Transformer optimization and evaluation. No file, DB, or tracking I/O."""
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from harp.core.training.metrics import calc_binary_metrics
from .config import NnTrainRecipe
from .contracts import NnInputContractError
from .dataset import NnRaceDataset, collate_nn_races
from .losses import nn_place_loss
from .networks.factory import build_nn_network
from .tensor_batch import NnInputSpec, NnTensorBatch


def iter_nn_batches(dataset, batch_size, device, *, seed=None, num_workers=0):
    generator = torch.Generator().manual_seed(0 if seed is None else seed)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=seed is not None,
                        collate_fn=collate_nn_races, num_workers=num_workers,
                        generator=generator, drop_last=False)
    for batch in loader:
        yield NnTensorBatch.from_numpy(batch, device)


@dataclass
class NnTrainingState:
    model: torch.nn.Module
    optimizer: torch.optim.Optimizer
    scheduler: torch.optim.lr_scheduler.ReduceLROnPlateau
    epoch: int = 0
    global_step: int = 0
    best_epoch: int = 0
    best_logloss: float = float("inf")
    stopping_reference: float = float("inf")
    bad_epochs: int = 0
    best_weights: dict | None = None
    metrics_history: list[dict] = field(default_factory=list)


def initialize_nn_training(spec: NnInputSpec, recipe: NnTrainRecipe, device: str) -> NnTrainingState:
    torch.manual_seed(recipe.training.seed)
    model = build_nn_network(spec, recipe.model).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=recipe.optimizer.lr, weight_decay=recipe.optimizer.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=recipe.scheduler.factor,
        patience=recipe.scheduler.patience, min_lr=recipe.scheduler.min_lr,
        threshold=recipe.early_stopping.min_delta, threshold_mode="abs",
    )
    return NnTrainingState(model, optimizer, scheduler)


def train_one_nn_epoch(state: NnTrainingState, dataset: NnRaceDataset,
                       recipe: NnTrainRecipe, device: str) -> dict:
    if not len(dataset):
        raise NnInputContractError("NN training split is empty")
    state.model.train()
    total_loss, count = 0.0, 0
    epoch = state.epoch + 1
    for batch in iter_nn_batches(dataset, recipe.training.batch_size_races, device,
                                  seed=(recipe.training.seed + epoch) % (2**63), num_workers=recipe.runtime.num_workers):
        if not torch.equal(batch.label_mask, batch.features.entrant_mask):
            raise NnInputContractError("NN training requires whole races with complete targets")
        state.optimizer.zero_grad(set_to_none=True)
        logits = state.model(batch.features)
        loss = nn_place_loss(logits, batch.labels, batch.features.entrant_mask, batch.label_mask)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(state.model.parameters(), recipe.training.gradient_clip_norm, error_if_nonfinite=True)
        state.optimizer.step()
        size = int(batch.label_mask.sum().item())
        total_loss += float(loss.detach().item()) * size
        count += size
        state.global_step += 1
    state.epoch = epoch
    return {"logloss": total_loss / count, "entries": count, "races": len(dataset)}


@dataclass(frozen=True)
class NnEvaluation:
    metrics: dict
    predictions: pd.DataFrame


def evaluate_nn(model, dataset: NnRaceDataset, *, batch_size: int, device: str, num_workers=0) -> NnEvaluation:
    if not len(dataset):
        raise NnInputContractError("NN evaluation split is empty")
    model.eval()
    loss_sum, label_count = 0.0, 0
    records, targets, probabilities = [], [], []
    with torch.inference_mode():
        for batch in iter_nn_batches(dataset, batch_size, device, num_workers=num_workers):
            logits = model(batch.features)
            valid = batch.features.entrant_mask
            if not torch.isfinite(logits[valid]).all():
                raise NnInputContractError("non-finite NN prediction")
            proba = torch.sigmoid(logits)
            known = valid & batch.label_mask
            size = int(known.sum().item())
            if size:
                loss_sum += float(nn_place_loss(logits, batch.labels, valid, batch.label_mask).item()) * size
                label_count += size
                targets.extend(batch.labels[known].cpu().tolist())
                probabilities.extend(proba[known].cpu().tolist())
            values = proba.cpu().numpy()
            for i, race_id in enumerate(batch.race_ids):
                for j, horse_id in enumerate(batch.horse_ids[i]):
                    if horse_id is not None:
                        records.append((race_id, horse_id, float(values[i, j])))
    metrics = calc_binary_metrics(pd.Series(targets), np.asarray(probabilities)) if label_count else {}
    if label_count:
        # Stable even for a single-class validation split and variable field sizes.
        metrics["logloss"] = loss_sum / label_count
    metrics.update(entries=len(records), labelled_entries=label_count, races=len(dataset))
    return NnEvaluation(metrics, pd.DataFrame(records, columns=["race_id", "kettonum", "place_probability"]))


def _cpu_copy(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: _cpu_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_cpu_copy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_cpu_copy(item) for item in value)
    return deepcopy(value)


def update_nn_selection(state: NnTrainingState, validation: NnEvaluation, recipe: NnTrainRecipe) -> bool:
    metric = validation.metrics.get("logloss")
    if metric is None or not np.isfinite(metric):
        raise NnInputContractError("validation requires finite logloss and known targets")
    if metric < state.best_logloss:
        state.best_logloss, state.best_epoch = metric, state.epoch
        state.best_weights = _cpu_copy(state.model.state_dict())
    if metric < state.stopping_reference - recipe.early_stopping.min_delta:
        state.stopping_reference, state.bad_epochs = metric, 0
    else:
        state.bad_epochs += 1
    state.scheduler.step(metric)
    return state.bad_epochs >= recipe.early_stopping.patience


def capture_nn_checkpoint(state: NnTrainingState, device: str) -> dict:
    if state.best_weights is None:
        raise NnInputContractError("cannot checkpoint before validation")
    rng = {"cpu": torch.get_rng_state()}
    if device == "cuda":
        rng["cuda"] = torch.cuda.get_rng_state_all()
    elif device == "mps":
        rng["mps"] = torch.mps.get_rng_state()
    return _cpu_copy({
        "version": 1, "model": state.model.state_dict(), "optimizer": state.optimizer.state_dict(),
        "scheduler": state.scheduler.state_dict(), "epoch": state.epoch, "global_step": state.global_step,
        "best_epoch": state.best_epoch, "best_logloss": state.best_logloss,
        "stopping_reference": state.stopping_reference, "bad_epochs": state.bad_epochs,
        "best_weights": state.best_weights, "metrics_history": state.metrics_history, "rng": rng,
    })


def restore_nn_checkpoint(state: NnTrainingState, checkpoint: dict, device: str) -> None:
    if checkpoint.get("version") != 1:
        raise NnInputContractError("unsupported NN checkpoint version")
    state.model.load_state_dict(checkpoint["model"], strict=True)
    state.optimizer.load_state_dict(checkpoint["optimizer"])
    state.scheduler.load_state_dict(checkpoint["scheduler"])
    for name in ("epoch", "global_step", "best_epoch", "best_logloss", "stopping_reference", "bad_epochs", "metrics_history"):
        setattr(state, name, deepcopy(checkpoint[name]))
    state.best_weights = _cpu_copy(checkpoint["best_weights"])
    torch.set_rng_state(checkpoint["rng"]["cpu"])
    if device == "cuda":
        torch.cuda.set_rng_state_all(checkpoint["rng"]["cuda"])
    elif device == "mps":
        torch.mps.set_rng_state(checkpoint["rng"]["mps"])
