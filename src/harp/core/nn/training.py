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
from .losses import (
    nn_odds_loss,
    nn_place_loss,
    nn_probabilities,
    nn_rank_objective,
    nn_win_loss,
)
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
    model = build_nn_network(spec, recipe.model, rank_auxiliary=recipe.auxiliary_rank is not None,
                             odds_auxiliary=recipe.auxiliary_odds is not None).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=recipe.optimizer.lr, weight_decay=recipe.optimizer.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=recipe.scheduler.factor,
        patience=recipe.scheduler.patience, min_lr=recipe.scheduler.min_lr,
        threshold=recipe.early_stopping.min_delta, threshold_mode="abs",
    )
    return NnTrainingState(model, optimizer, scheduler)


@dataclass
class _RankMetrics:
    loss_sum: float = 0.0
    accuracy_sum: float = 0.0
    races: int = 0
    comparable_races: int = 0
    pairs: int = 0

    def add(self, result):
        self.loss_sum += float(result.race_loss.detach().sum().item())
        self.accuracy_sum += float(result.race_accuracy.detach().sum().item())
        self.races += len(result.pair_counts)
        self.comparable_races += int(result.pair_counts.gt(0).sum().item())
        self.pairs += int(result.pair_counts.sum().item())

    def values(self):
        return {"rank_loss": self.loss_sum / self.races if self.pairs else None,
                "rank_pair_accuracy": self.accuracy_sum / self.comparable_races if self.comparable_races else None,
                "rank_pairs": self.pairs, "rank_races": self.comparable_races}


@dataclass
class _OddsMetrics:
    loss_sum: float = 0.0
    absolute_sum: float = 0.0
    square_sum: float = 0.0
    entries: int = 0

    def add(self, loss, scores, batch, scale):
        known = batch.features.entrant_mask & batch.odds_mask
        errors = (scores[known] - batch.odds_target[known]).detach() * scale
        count = int(known.sum().item())
        self.entries += count
        self.loss_sum += float(loss.detach().item()) * count
        self.absolute_sum += float(errors.abs().sum().item())
        self.square_sum += float(errors.square().sum().item())

    def values(self):
        return {"odds_huber": self.loss_sum / self.entries if self.entries else None,
                "odds_log_mae": self.absolute_sum / self.entries if self.entries else None,
                "odds_log_rmse": (self.square_sum / self.entries) ** .5 if self.entries else None,
                "odds_entries": self.entries}


def train_one_nn_epoch(state: NnTrainingState, dataset: NnRaceDataset,
                       recipe: NnTrainRecipe, device: str) -> dict:
    if not len(dataset):
        raise NnInputContractError("NN training split is empty")
    if dataset.task != recipe.task:
        raise NnInputContractError("NN Dataset task differs from training task")
    state.model.train()
    total_loss, count, entries = 0.0, 0, 0
    rank_metrics = _RankMetrics()
    odds_metrics = _OddsMetrics()
    epoch = state.epoch + 1
    for batch in iter_nn_batches(dataset, recipe.training.batch_size_races, device,
                                  seed=(recipe.training.seed + epoch) % (2**63), num_workers=recipe.runtime.num_workers):
        if not torch.equal(batch.label_mask, batch.features.entrant_mask):
            raise NnInputContractError("NN training requires whole races with complete targets")
        state.optimizer.zero_grad(set_to_none=True)
        output = state.model.forward_outputs(batch.features)
        logits = output.logits
        loss_fn = nn_win_loss if recipe.task == "win" else nn_place_loss
        main_loss = loss_fn(logits, batch.labels, batch.features.entrant_mask, batch.label_mask)
        loss = main_loss
        if recipe.auxiliary_rank is not None:
            if output.rank_scores is None:
                raise NnInputContractError("auxiliary ranking requires a rank head")
            rank = nn_rank_objective(output.rank_scores, batch.finish_order,
                                     batch.features.entrant_mask, batch.finish_order_mask)
            rank_metrics.add(rank)
            # Weight zero is the main-only control, including gradient clipping
            # and optimizer state: no rank gradients or weight decay updates.
            if recipe.auxiliary_rank.weight > 0:
                loss = loss + recipe.auxiliary_rank.weight * rank.loss
        if recipe.auxiliary_odds is not None:
            if output.odds_scores is None:
                raise NnInputContractError("auxiliary odds requires an odds head")
            odds_loss = nn_odds_loss(output.odds_scores, batch.odds_target, batch.features.entrant_mask, batch.odds_mask)
            odds_metrics.add(odds_loss, output.odds_scores, batch, dataset.odds_scale)
            if recipe.auxiliary_odds.weight > 0:
                loss = loss + recipe.auxiliary_odds.weight * odds_loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(state.model.parameters(), recipe.training.gradient_clip_norm, error_if_nonfinite=True)
        state.optimizer.step()
        batch_entries = int(batch.label_mask.sum().item())
        size = len(batch.race_ids) if recipe.task == "win" else batch_entries
        total_loss += float(main_loss.detach().item()) * size
        count += size
        entries += batch_entries
        state.global_step += 1
    state.epoch = epoch
    metrics = {"logloss": total_loss / count, "entries": entries, "races": len(dataset)}
    if recipe.auxiliary_rank is not None:
        metrics.update(rank_metrics.values())
        # Recombine epoch components with their own denominators: place BCE is
        # entrant-mean while the auxiliary loss is race-mean.
        metrics["total_loss"] = metrics["logloss"] + recipe.auxiliary_rank.weight * rank_metrics.loss_sum / rank_metrics.races
    if recipe.auxiliary_odds is not None:
        metrics.update(odds_metrics.values())
        metrics["total_loss"] = metrics.get("total_loss", metrics["logloss"]) + recipe.auxiliary_odds.weight * (metrics["odds_huber"] or 0)
    return metrics


@dataclass(frozen=True)
class NnEvaluation:
    metrics: dict
    predictions: pd.DataFrame
    calibration_samples: pd.DataFrame


def evaluate_nn(model, dataset: NnRaceDataset, *, batch_size: int, device: str, num_workers=0) -> NnEvaluation:
    if not len(dataset):
        raise NnInputContractError("NN evaluation split is empty")
    model.eval()
    loss_sum, label_count, loss_count = 0.0, 0, 0
    race_brier_sum, top1_sum = 0.0, 0
    records, targets, probabilities = [], [], []
    rank_metrics = _RankMetrics()
    odds_metrics = _OddsMetrics()
    has_rank = False
    has_odds = False
    with torch.inference_mode():
        for batch in iter_nn_batches(dataset, batch_size, device, num_workers=num_workers):
            output = model.forward_outputs(batch.features)
            logits = output.logits
            valid = batch.features.entrant_mask
            if not torch.isfinite(logits[valid]).all():
                raise NnInputContractError("non-finite NN prediction")
            proba = nn_probabilities(logits, valid, dataset.task)
            known = valid & batch.label_mask
            if dataset.task == "win":
                # Predictions cover every field; metrics only cover complete,
                # single-winner races. Never score a partially observed field.
                complete = (known == valid).all(dim=1)
                winners = batch.labels.masked_fill(~known, 0).sum(dim=1)
                eligible = complete & winners.eq(1)
                known = known & eligible.unsqueeze(-1)
                races = int(eligible.sum().item())
                if races:
                    loss_sum += float(nn_win_loss(logits[eligible], batch.labels[eligible],
                                                  valid[eligible], batch.label_mask[eligible]).item()) * races
                    loss_count += races
                    errors = (proba[eligible] - batch.labels[eligible]).masked_fill(~valid[eligible], 0)
                    race_brier_sum += float(errors.square().sum().item())
                    winner = batch.labels[eligible].masked_fill(~valid[eligible], 0).argmax(dim=1)
                    top1_sum += int(proba[eligible].argmax(dim=1).eq(winner).sum().item())
            if output.rank_scores is not None:
                has_rank = True
                rank_metrics.add(nn_rank_objective(output.rank_scores, batch.finish_order,
                                                   valid, batch.finish_order_mask & known))
            if output.odds_scores is not None:
                has_odds = True
                odds_loss = nn_odds_loss(output.odds_scores, batch.odds_target, valid, batch.odds_mask)
                odds_metrics.add(odds_loss, output.odds_scores, batch, dataset.odds_scale)
            size = int(known.sum().item())
            if size:
                if dataset.task == "place":
                    loss_sum += float(nn_place_loss(logits, batch.labels, valid, known).item()) * size
                    loss_count += size
                label_count += size
                targets.extend(batch.labels[known].cpu().tolist())
                probabilities.extend(proba[known].cpu().tolist())
            values = proba.cpu().numpy()
            batch_labels = batch.labels.cpu().numpy()
            batch_label_mask = known.cpu().numpy()
            for i, race_id in enumerate(batch.race_ids):
                for j, horse_id in enumerate(batch.horse_ids[i]):
                    if horse_id is not None:
                        label = float(batch_labels[i, j]) if batch_label_mask[i, j] else np.nan
                        records.append((race_id, horse_id, float(values[i, j]), label))
    metrics = calc_binary_metrics(pd.Series(targets), np.asarray(probabilities)) if label_count else {}
    if label_count:
        # Stable even for a single-class validation split and variable field sizes.
        if dataset.task == "win":
            metrics["binary_logloss"] = metrics["logloss"]
            metrics.update(race_brier=race_brier_sum / loss_count,
                           top1_accuracy=top1_sum / loss_count, labelled_races=loss_count)
        metrics["logloss"] = loss_sum / loss_count
    metrics.update(entries=len(records), labelled_entries=label_count, races=len(dataset))
    if has_rank:
        metrics.update(rank_metrics.values())
    if has_odds:
        metrics.update(odds_metrics.values())
    probability_column = f"{dataset.task}_probability"
    frame = pd.DataFrame(records, columns=["race_id", "kettonum", probability_column, "y_true"])
    return NnEvaluation(metrics, frame[["race_id", "kettonum", probability_column]],
                        frame.rename(columns={probability_column: "probability"}))


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
