from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import FileGatewayPort, TableParquetExportPort


@dataclass(frozen=True)
class ExportTableToParquetRequest:
    source_table: str
    output_path: str
    where: dict[str, object] | None
    compression: str
    overwrite: bool
    quiet: bool


@dataclass(frozen=True)
class ExportTableToParquetDeps:
    file_gateway: FileGatewayPort
    parquet_exporter: TableParquetExportPort


@dataclass(frozen=True)
class ExportTableToParquetResult:
    source_table: str
    output_path: str
    row_count: int
    file_size_bytes: int
    compression: str
