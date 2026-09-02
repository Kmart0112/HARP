from __future__ import annotations

from dataclasses import dataclass

from harp.config import DatabaseConfig
from harp.usecase import (
    ExportTableToParquetRequest,
    run_export_table_to_parquet_usecase,
)

from .deps import build_table_parquet_export_deps as _build_table_parquet_export_deps


@dataclass(frozen=True)
class ExportTableToParquetCommand:
    """Command values for exporting a database table to Parquet.

    Args:
        source_table: Database table to export.
        output_path: Destination Parquet path.
        where: Optional filter expression map for the exporter.
        compression: Parquet compression codec.
        overwrite: Whether an existing output may be replaced.
        quiet: Suppress non-essential output.
    """

    source_table: str
    output_path: str
    where: dict[str, object] | None
    compression: str
    overwrite: bool
    quiet: bool


class TableParquetExportController:
    """Build table export usecase input from a command."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    def run(self, cmd: ExportTableToParquetCommand):
        """Export a source table to a Parquet file.

        Args:
            cmd: CLI-level command values for the export.
        """

        req = ExportTableToParquetRequest(
            source_table=cmd.source_table,
            output_path=cmd.output_path,
            where=cmd.where,
            compression=cmd.compression,
            overwrite=cmd.overwrite,
            quiet=cmd.quiet,
        )
        deps = _build_table_parquet_export_deps(self._config)
        return run_export_table_to_parquet_usecase(req, deps)
