from typing import Protocol

from harp.core.nn.odds_targets import (
    FinalPlaceOddsBatch,
    FinalPlaceOddsQuery,
    NnOddsSnapshot,
)


class FinalPlaceOddsRepositoryPort(Protocol):
    def load(self, query: FinalPlaceOddsQuery) -> FinalPlaceOddsBatch:
        """One row for every requested key, preserving absent source rows."""
        ...


class NnOddsSnapshotStorePort(Protocol):
    def save(self, snapshot: NnOddsSnapshot) -> str:
        """Atomically publish teachers and provenance; return content identity."""
        ...

    def load(self, snapshot_id: str) -> NnOddsSnapshot:
        """Validate persisted teachers and coverage without any DB access."""
        ...
