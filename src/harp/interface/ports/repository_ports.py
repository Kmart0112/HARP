from __future__ import annotations

from typing import Protocol

from harp.core.race_inputs import RaceInputQuery, RaceInputs


class InferenceRepositoryPort(Protocol):
    def load_prediction_input(self, query: RaceInputQuery) -> RaceInputs:
        """Return one coherent batch with logical fields and no post-race targets.

        Preserve every requested active entrant even when odds are unavailable.
        Raise OddsContractError for unsupported schemas, keys, types or policies.
        """
        ...


class TrainingRepositoryPort(Protocol):
    def load_training_input(self, query: RaceInputQuery) -> RaceInputs:
        """Return pre-start inputs, retaining missing odds for coverage auditing.

        The result must satisfy the query and have one row per active entrant.
        """
        ...
