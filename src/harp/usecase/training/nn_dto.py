from dataclasses import dataclass

from harp.core.nn.config import NnTrainRecipe
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetStorePort
from harp.interface.ports.nn_training_ports import NnModelStorePort
from harp.interface.ports.tracking_ports import TrackingPort


@dataclass(frozen=True)
class NnTrainRequest:
    prepared_dataset_id: str
    recipe: NnTrainRecipe
    device: str
    provenance: dict
    resume_run_id: str | None = None
    tracking_experiment: str | None = None


@dataclass(frozen=True)
class NnTrainDeps:
    input_store: NnDatasetStorePort
    prepared_store: NnPreparedDatasetStorePort
    model_store: NnModelStorePort
    tracking: TrackingPort | None = None


@dataclass(frozen=True)
class NnTrainResult:
    run_id: str
    checkpoint_id: str
    prepared_dataset_id: str
    completed_epochs: int
    best_epoch: int
    best_validation_logloss: float
    stopped_early: bool
    split_summary: dict
    tracking_run_id: str | None


@dataclass(frozen=True)
class NnEvaluateRequest:
    run_id: str
    device: str
    split: str = "test"
    checkpoint_id: str | None = None
    batch_size: int = 32


@dataclass(frozen=True)
class NnEvaluateResult:
    run_id: str
    checkpoint_id: str
    prepared_dataset_id: str
    split: str
    best_epoch: int
    metrics: dict
