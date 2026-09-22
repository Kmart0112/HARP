from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from harp.core.race_inputs import RaceInputs


@dataclass(frozen=True)
class StoredPredictionInputs:
    inputs: RaceInputs
    metadata: dict


class PredictionSnapshotStorePort(Protocol):
    def save(self, inputs: RaceInputs, metadata: dict) -> str:
        """Atomically publish immutable inputs; return their content identity."""
        ...

    def load(self, snapshot_id: str) -> StoredPredictionInputs:
        """Verify integrity and contract version before exposing persisted inputs."""
        ...
