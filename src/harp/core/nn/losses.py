from dataclasses import dataclass

import torch
from torch.nn import functional as F

from .contracts import NnInputContractError
from .tasks import nn_target


@dataclass(frozen=True)
class NnRankObjective:
    race_loss: torch.Tensor
    race_accuracy: torch.Tensor
    pair_counts: torch.Tensor

    @property
    def loss(self):
        return self.race_loss.mean()


def nn_rank_objective(scores, finish_order, entrant_mask, finish_order_mask) -> NnRankObjective:
    """One oriented comparison per unequal-rank pair, then equal race weights.

    Unknown targets and padding never form pairs. Ties are not ordered. A race
    with no comparable pair contributes zero loss and no accuracy observation.
    """
    if (scores.ndim != 2 or not len(scores) or scores.shape != finish_order.shape
            or scores.shape != entrant_mask.shape or scores.shape != finish_order_mask.shape):
        raise NnInputContractError("rank objective requires aligned nonempty race batches")
    valid = entrant_mask & finish_order_mask
    orders = finish_order[valid]
    if not (torch.isfinite(orders) & orders.gt(0) & orders.eq(orders.floor())).all():
        raise NnInputContractError("rank objective requires positive integer finishing positions")
    if not torch.isfinite(scores[valid]).all():
        raise NnInputContractError("non-finite NN rank scores")
    safe_scores = scores.masked_fill(~valid, 0)
    safe_orders = finish_order.masked_fill(~valid, 0)
    pairs = valid.unsqueeze(2) & valid.unsqueeze(1) & (safe_orders.unsqueeze(2) < safe_orders.unsqueeze(1))
    differences = safe_scores.unsqueeze(2) - safe_scores.unsqueeze(1)
    counts = pairs.sum(dim=(1, 2))
    denominator = counts.clamp_min(1)
    loss = F.softplus(-differences).masked_fill(~pairs, 0).sum(dim=(1, 2)) / denominator
    correct = (differences.gt(0).to(scores.dtype) + .5 * differences.eq(0)).masked_fill(~pairs, 0)
    accuracy = correct.sum(dim=(1, 2)) / denominator
    return NnRankObjective(loss, accuracy, counts)


def nn_place_loss(logits, labels, entrant_mask, label_mask):
    valid = entrant_mask & label_mask
    if not valid.any():
        raise NnInputContractError("NN loss requires at least one known target")
    if not torch.isfinite(logits[valid]).all():
        raise NnInputContractError("non-finite NN logits")
    return F.binary_cross_entropy_with_logits(logits[valid], labels[valid], reduction="mean")


def nn_probabilities(logits, entrant_mask, task: str):
    """Normalize only real entrants; padding never receives probability mass."""
    nn_target(task)
    if (logits.ndim != 2 or logits.shape != entrant_mask.shape
            or not entrant_mask.any(dim=1).all()):
        raise NnInputContractError("NN probabilities require nonempty full fields")
    if not torch.isfinite(logits[entrant_mask]).all():
        raise NnInputContractError("non-finite NN logits")
    if task == "win":
        return torch.softmax(logits.masked_fill(~entrant_mask, -torch.inf), dim=1)
    return torch.sigmoid(logits).masked_fill(~entrant_mask, 0)


def nn_win_loss(logits, labels, entrant_mask, label_mask):
    """Mean winner cross entropy per race, with exactly one known winner."""
    if (logits.ndim != 2 or logits.shape != entrant_mask.shape or labels.shape != logits.shape
            or label_mask.shape != logits.shape or not entrant_mask.any(dim=1).all()
            or not torch.equal(entrant_mask, label_mask)):
        raise NnInputContractError("win loss requires complete labels for every entrant")
    known = labels[entrant_mask]
    if not ((known == 0) | (known == 1)).all():
        raise NnInputContractError("win loss requires binary labels")
    safe_labels = labels.masked_fill(~entrant_mask, 0)
    if not safe_labels.sum(dim=1).eq(1).all():
        raise NnInputContractError("win loss requires exactly one winner per race")
    if not torch.isfinite(logits[entrant_mask]).all():
        raise NnInputContractError("non-finite NN logits")
    return F.cross_entropy(logits.masked_fill(~entrant_mask, -torch.inf), safe_labels.argmax(dim=1))


def nn_odds_loss(scores, targets, entrant_mask, target_mask):
    """Delta=1 Huber on standardized log odds, averaged over available entrants."""
    known = entrant_mask & target_mask
    if scores.shape != targets.shape or scores.shape != known.shape:
        raise NnInputContractError("odds score and target shapes differ")
    if not torch.isfinite(scores[known]).all() or not torch.isfinite(targets[known]).all():
        raise NnInputContractError("non-finite available odds prediction or target")
    if not known.any():
        return scores[known].sum()
    return torch.nn.functional.huber_loss(scores[known], targets[known], reduction="mean", delta=1.0)
