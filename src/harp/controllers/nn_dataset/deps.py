from contextlib import contextmanager

from sqlalchemy import create_engine

from harp.adapters.driven.db.nn_input_repository import NnInputMapping, SqlNnInputRepository
from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_feature_contract import JsonNnFeatureContractReader
from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
from harp.usecase.nn_dataset.dto import NnDatasetDeps


def load_nn_feature_contract(path: str):
    return JsonNnFeatureContractReader().load(path)


@contextmanager
def build_nn_dataset_deps(input_root: str, prepared_root: str, *, db_url: str | None = None, contract=None):
    engine = create_engine(db_url) if db_url is not None else None
    try:
        yield NnDatasetDeps(
            input_store=ParquetNnDatasetStore(input_root),
            prepared_store=JsonNnPreparedDatasetStore(prepared_root),
            repository=SqlNnInputRepository(engine=engine, mapping=NnInputMapping(), contract=contract) if engine is not None else None,
        )
    finally:
        if engine is not None:
            engine.dispose()
