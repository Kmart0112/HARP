import torch
from torch.nn import functional as F

from .contracts import NnInputContractError


def nn_place_loss(logits, labels, entrant_mask, label_mask):
    valid = entrant_mask & label_mask
    if not valid.any():
        raise NnInputContractError("NN loss requires at least one known target")
    if not torch.isfinite(logits[valid]).all():
        raise NnInputContractError("non-finite NN logits")
    return F.binary_cross_entropy_with_logits(logits[valid], labels[valid], reduction="mean")
