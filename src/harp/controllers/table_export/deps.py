from __future__ import annotations

from harp.adapters.driven import (
    LocalFileGatewayAdapter,
    PostgresCopyCsvParquetExportAdapter,
)
from harp.config import DatabaseConfig
from harp.usecase import ExportTableToParquetDeps


def build_table_parquet_export_deps(config: DatabaseConfig) -> ExportTableToParquetDeps:
    return ExportTableToParquetDeps(
        file_gateway=LocalFileGatewayAdapter(),
        parquet_exporter=PostgresCopyCsvParquetExportAdapter(db_url=config.db_url),
    )
