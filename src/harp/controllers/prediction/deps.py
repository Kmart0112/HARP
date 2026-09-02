from __future__ import annotations

from harp.adapters.driven.db import PostgresPolarsInferenceRepositoryAdapter
from harp.adapters.driven.storage import (
    JsonManifestReaderAdapter,
    LocalFileGatewayAdapter,
    PickleModelLoaderAdapter,
)
from harp.config import HarpRuntimeConfig
from harp.usecase.prediction.place import PredictPlaceDeps


def build_predict_place_deps(
    config: HarpRuntimeConfig,
    *,
    file_gateway: LocalFileGatewayAdapter | None = None,
) -> PredictPlaceDeps:
    resolved_file_gateway = file_gateway or LocalFileGatewayAdapter()
    return PredictPlaceDeps(
        inference_repository=PostgresPolarsInferenceRepositoryAdapter(
            db_url=config.database.db_url,
        ),
        model_loader_port=PickleModelLoaderAdapter(),
        manifest_reader_port=JsonManifestReaderAdapter(file_gateway=resolved_file_gateway),
        file_gateway=resolved_file_gateway,
        mart_table=config.mart.prediction_mart_table,
    )
