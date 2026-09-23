from dataclasses import dataclass

from harp.core.nn.contracts import NnInputContractError, NnInputQuery
from harp.core.nn.split import NnDatasetConfig
from harp.interface.ports.nn_input_ports import NnInputRepositoryPort
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetStorePort
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort


@dataclass(frozen=True)
class PrepareNnDatasetRequest:
    config: NnDatasetConfig
    input_dataset_id: str | None = None
    query: NnInputQuery | None = None

    def __post_init__(self):
        if (self.input_dataset_id is None) == (self.query is None):
            raise NnInputContractError("choose either saved input identity or DB input query")


@dataclass(frozen=True)
class NnDatasetDeps:
    input_store: NnDatasetStorePort
    prepared_store: NnPreparedDatasetStorePort
    repository: NnInputRepositoryPort | None = None


@dataclass(frozen=True)
class PrepareNnDatasetResult:
    input_dataset_id: str
    prepared_dataset_id: str
    summary: dict
