from contextlib import contextmanager

from sqlalchemy import create_engine

from harp.adapters.driven.db.final_odds_repository import (
    FinalOddsMapping,
    SqlFinalPlaceOddsRepository,
)
from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_odds_snapshot_store import (
    ParquetNnOddsSnapshotStore,
)
from harp.adapters.driven.storage.nn_prepared_dataset_store import (
    JsonNnPreparedDatasetStore,
)
from harp.usecase.nn_dataset.odds import CaptureNnFinalOddsDeps


@contextmanager
def build_nn_odds_deps(input_root, prepared_root, output_root, *, db_url, batch_size):
    engine = create_engine(db_url)
    try:
        yield CaptureNnFinalOddsDeps(
            ParquetNnDatasetStore(input_root), JsonNnPreparedDatasetStore(prepared_root),
            SqlFinalPlaceOddsRepository(engine=engine, mapping=FinalOddsMapping(), batch_size=batch_size),
            ParquetNnOddsSnapshotStore(output_root))
    finally:
        engine.dispose()
