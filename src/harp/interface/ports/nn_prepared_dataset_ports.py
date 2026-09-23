from dataclasses import dataclass
from typing import Protocol

from harp.core.nn.preprocessing import NnPreprocessingState
from harp.core.nn.split import NnDatasetConfig, NnRacePartition


@dataclass(frozen=True)
class NnPreparedDatasetRecipe:
    input_dataset_id: str
    config: NnDatasetConfig
    preprocessing: NnPreprocessingState
    partitions: tuple[NnRacePartition, ...]


class NnPreparedDatasetStorePort(Protocol):
    def save(self, recipe: NnPreparedDatasetRecipe) -> str:
        """Publish input identity, fitted transforms and race splits atomically."""
        ...

    def load(self, prepared_dataset_id: str) -> NnPreparedDatasetRecipe:
        """Verify and load the preparation recipe; no DB access or refitting."""
        ...
