"""Tensor features are separated structurally from targets and identity metadata."""
from dataclasses import dataclass, fields

import torch

from .preprocessing import NnPreprocessingState


@dataclass(frozen=True)
class NnInputSpec:
    current_numeric: tuple[str, ...]
    current_categories: tuple[tuple[str, int], ...]
    history_numeric: tuple[str, ...]
    history_categories: tuple[tuple[str, int], ...]

    @classmethod
    def from_preprocessing(cls, preprocessing: NnPreprocessingState):
        return cls(preprocessing.current.numeric_names,
                   tuple((state.name, state.cardinality) for state in preprocessing.current.categorical),
                   preprocessing.history.numeric_names,
                   tuple((state.name, state.cardinality) for state in preprocessing.history.categorical))


@dataclass(frozen=True)
class NnModelInputs:
    current_numeric: torch.Tensor
    current_numeric_missing: torch.Tensor
    current_categorical: torch.Tensor
    history_numeric: torch.Tensor
    history_numeric_missing: torch.Tensor
    history_categorical: torch.Tensor
    history_relative: torch.Tensor
    entrant_mask: torch.Tensor
    history_mask: torch.Tensor

    @classmethod
    def from_numpy(cls, batch: dict, device: str):
        return cls(**{field.name: torch.as_tensor(batch[field.name], device=device) for field in fields(cls)})


@dataclass(frozen=True)
class NnTensorBatch:
    features: NnModelInputs
    labels: torch.Tensor
    label_mask: torch.Tensor
    race_ids: tuple[str, ...]
    horse_ids: tuple[tuple[str | None, ...], ...]
    finish_order: torch.Tensor
    finish_order_mask: torch.Tensor
    odds_target: torch.Tensor
    odds_mask: torch.Tensor

    @classmethod
    def from_numpy(cls, batch: dict, device: str):
        return cls(NnModelInputs.from_numpy(batch, device),
                   torch.as_tensor(batch["labels"], device=device),
                   torch.as_tensor(batch["label_mask"], device=device),
                   batch["race_ids"], batch["horse_ids"],
                   torch.as_tensor(batch["finish_order"], device=device),
                   torch.as_tensor(batch["finish_order_mask"], device=device),
                   torch.as_tensor(batch["odds_target"], device=device),
                   torch.as_tensor(batch["odds_mask"], device=device))


@dataclass(frozen=True)
class NnNetworkOutput:
    logits: torch.Tensor
    rank_scores: torch.Tensor | None = None
    odds_scores: torch.Tensor | None = None
