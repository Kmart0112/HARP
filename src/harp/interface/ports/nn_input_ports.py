from typing import Protocol

from harp.core.nn.contracts import NnFeatureContract, NnInputQuery, NnRaceInputs, NnTrainingInputs


class NnInputRepositoryPort(Protocol):
    def load_training_inputs(self, query: NnInputQuery) -> NnTrainingInputs:
        """Keep complete fields and nullable targets, returning deduplicated history prefixes."""
        ...

    def load_prediction_inputs(self, query: NnInputQuery) -> NnRaceInputs:
        """Return only pre-race entries and their past runs; never read current targets."""
        ...


class NnFeatureContractPort(Protocol):
    def load(self, path: str) -> NnFeatureContract:
        """Read the versioned feature allowlist exported from dbt, without guessing columns."""
        ...
