from dataclasses import dataclass
from typing import Protocol

from harp.core.nn.config import NnTrainRecipe
from harp.core.nn.preprocessing import NnPreprocessingState


@dataclass(frozen=True)
class StoredNnCheckpoint:
    run_id: str
    checkpoint_id: str
    metadata: dict
    checkpoint: dict
    artifact_path: str
    recipe: NnTrainRecipe
    preprocessing: NnPreprocessingState


class NnTrainingRecipePort(Protocol):
    def load(self, path: str) -> dict:
        """Parse a recipe document; semantic resolution belongs to Core/Controller."""
        ...

    def parse_overrides(self, values: tuple[str, ...]) -> dict:
        """Parse explicit dotted-key literal values, not executable expressions."""
        ...


class NnModelStorePort(Protocol):
    def create_run(self, metadata: dict) -> str:
        """Allocate an isolated training run with immutable resolved metadata."""
        ...

    def save_checkpoint(self, run_id: str, checkpoint: dict) -> str:
        """Atomically publish an epoch snapshot and update the latest pointer."""
        ...

    def load_checkpoint(self, run_id: str, checkpoint_id: str | None = None) -> StoredNnCheckpoint:
        """Verify all files and return portable state, preprocessing and configuration."""
        ...
