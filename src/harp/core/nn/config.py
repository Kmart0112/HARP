"""Typed training recipes. Values come from the caller, never files or settings."""
from copy import deepcopy
from dataclasses import dataclass
import math

from .contracts import NnInputContractError


def _integer(name, value, minimum=1):
    if type(value) is not int or value < minimum:
        raise NnInputContractError(f"{name} must be an integer >= {minimum}")


def _number(name, value, minimum=0, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise NnInputContractError(f"{name} must be a finite number")
    if value < minimum or (positive and value == minimum):
        raise NnInputContractError(f"invalid {name}")


@dataclass(frozen=True)
class NnModelConfig:
    name: str
    d_model: int
    categorical_embedding_dim: int
    history_layers: int
    race_layers: int
    attention_heads: int
    feedforward_dim: int
    dropout: float

    def __post_init__(self):
        if self.name != "history_set_transformer_v1":
            raise NnInputContractError("unsupported NN architecture")
        for name in ("d_model", "categorical_embedding_dim", "history_layers", "race_layers", "attention_heads", "feedforward_dim"):
            _integer(name, getattr(self, name))
        if self.d_model % self.attention_heads:
            raise NnInputContractError("d_model must be divisible by attention_heads")
        _number("dropout", self.dropout)
        if self.dropout >= 1:
            raise NnInputContractError("dropout must be below 1")


@dataclass(frozen=True)
class NnOptimizerConfig:
    name: str
    lr: float
    weight_decay: float

    def __post_init__(self):
        if self.name != "adamw":
            raise NnInputContractError("unsupported NN optimizer")
        _number("lr", self.lr, positive=True)
        _number("weight_decay", self.weight_decay)


@dataclass(frozen=True)
class NnSchedulerConfig:
    name: str
    factor: float
    patience: int
    min_lr: float

    def __post_init__(self):
        if self.name != "reduce_on_plateau":
            raise NnInputContractError("unsupported NN scheduler")
        _number("scheduler.factor", self.factor, positive=True)
        if self.factor >= 1:
            raise NnInputContractError("scheduler.factor must be below 1")
        _integer("scheduler.patience", self.patience, 0)
        _number("scheduler.min_lr", self.min_lr, positive=True)


@dataclass(frozen=True)
class NnTrainingConfig:
    batch_size_races: int
    max_epochs: int
    seed: int
    gradient_clip_norm: float

    def __post_init__(self):
        _integer("batch_size_races", self.batch_size_races)
        _integer("max_epochs", self.max_epochs)
        _integer("seed", self.seed, 0)
        if self.seed >= 2**63:
            raise NnInputContractError("seed must be below 2**63")
        _number("gradient_clip_norm", self.gradient_clip_norm, positive=True)


@dataclass(frozen=True)
class NnLossConfig:
    name: str
    reduction: str

    def __post_init__(self):
        if self.name != "bce_with_logits" or self.reduction != "entrant_mean":
            raise NnInputContractError("NN v1 uses BCE logits averaged over valid entrants")


@dataclass(frozen=True)
class NnEarlyStoppingConfig:
    metric: str
    mode: str
    patience: int
    min_delta: float

    def __post_init__(self):
        if self.metric != "validation.logloss" or self.mode != "min":
            raise NnInputContractError("NN selection requires validation.logloss minimization")
        _integer("early_stopping.patience", self.patience)
        _number("early_stopping.min_delta", self.min_delta)


@dataclass(frozen=True)
class NnRuntimeConfig:
    device: str
    precision: str
    num_workers: int
    num_threads: int

    def __post_init__(self):
        if self.device not in {"auto", "cpu", "mps", "cuda"}:
            raise NnInputContractError("device must be auto, cpu, mps or cuda")
        if self.precision != "float32":
            raise NnInputContractError("NN v1 supports float32 precision")
        _integer("num_workers", self.num_workers, 0)
        _integer("num_threads", self.num_threads)


@dataclass(frozen=True)
class NnTrainRecipe:
    version: int
    model: NnModelConfig
    optimizer: NnOptimizerConfig
    scheduler: NnSchedulerConfig
    training: NnTrainingConfig
    loss: NnLossConfig
    early_stopping: NnEarlyStoppingConfig
    runtime: NnRuntimeConfig

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1:
            raise NnInputContractError("unsupported NN training recipe version")
        if self.scheduler.min_lr > self.optimizer.lr:
            raise NnInputContractError("min_lr cannot exceed initial lr")


def resolve_nn_training_recipe(document: dict, overrides: dict | None = None) -> NnTrainRecipe:
    """Apply explicit dotted-key values and reject unknown/missing settings."""
    if not isinstance(document, dict):
        raise NnInputContractError("NN training recipe must be a mapping")
    data = deepcopy(document)
    for key, value in (overrides or {}).items():
        parts = key.split(".")
        if len(parts) != 2 or not isinstance(data.get(parts[0]), dict) or parts[1] not in data[parts[0]]:
            raise NnInputContractError(f"unknown NN override: {key}")
        data[parts[0]][parts[1]] = value
    types = {"model": NnModelConfig, "optimizer": NnOptimizerConfig,
             "scheduler": NnSchedulerConfig, "training": NnTrainingConfig,
             "loss": NnLossConfig, "early_stopping": NnEarlyStoppingConfig,
             "runtime": NnRuntimeConfig}
    if set(data) != {"version", *types}:
        raise NnInputContractError("unknown or missing NN recipe sections")
    try:
        return NnTrainRecipe(data["version"], **{name: cls(**data[name]) for name, cls in types.items()})
    except (TypeError, KeyError) as exc:
        raise NnInputContractError("unknown, missing or invalid NN recipe fields") from exc
