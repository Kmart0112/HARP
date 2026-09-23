from dataclasses import dataclass
from typing import Protocol

from harp.core.nn.contracts import NnRaceInputs, NnTrainingInputs


@dataclass(frozen=True)
class StoredNnDataset:
    inputs: NnTrainingInputs
    metadata: dict


@dataclass(frozen=True)
class StoredNnPredictionInputs:
    inputs: NnRaceInputs
    metadata: dict


class NnDatasetStorePort(Protocol):
    def save(self, inputs: NnTrainingInputs, metadata: dict) -> str:
        """Atomically publish entries, shared histories and separate targets; return dataset ID."""
        ...

    def load(self, dataset_id: str) -> StoredNnDataset:
        """Verify version, hashes and logical invariants; never query the DB."""
        ...


class NnPredictionSnapshotPort(Protocol):
    def save(self, inputs: NnRaceInputs, metadata: dict) -> str:
        """Save the actual NN inputs. This v1 contract does not include odds or EV decisions."""
        ...

    def load(self, snapshot_id: str) -> StoredNnPredictionInputs:
        """Restore exactly the captured NN inputs, including their historical feature values."""
        ...
