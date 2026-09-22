from __future__ import annotations

from harp.adapters.driven.db.race_input_repository import (
    SqlRaceInputRepository,
    mart_input_mapping,
)
from harp.adapters.driven.storage import (
    JsonManifestReaderAdapter,
    LocalFileGatewayAdapter,
    PickleModelLoaderAdapter,
)
from harp.adapters.driven.storage.prediction_snapshot_store import (
    ParquetPredictionSnapshotStore,
)
from harp.config import HarpRuntimeConfig
from harp.shared.db import get_engine
from harp.usecase.prediction.place import PredictPlaceDeps


def build_predict_place_deps(
    config: HarpRuntimeConfig,
    *,
    file_gateway: LocalFileGatewayAdapter | None = None,
) -> PredictPlaceDeps:
    resolved_file_gateway = file_gateway or LocalFileGatewayAdapter()
    return PredictPlaceDeps(
        inference_repository=SqlRaceInputRepository(
            engine=get_engine(config.database.db_url),
            mapping=mart_input_mapping(config.mart.prediction_mart_table, quotes_table=config.mart.prediction_quotes_table),
        ),
        model_loader_port=PickleModelLoaderAdapter(),
        manifest_reader_port=JsonManifestReaderAdapter(file_gateway=resolved_file_gateway),
        file_gateway=resolved_file_gateway,
        snapshot_store=ParquetPredictionSnapshotStore(config.paths.prediction_snapshots_path),
    )
