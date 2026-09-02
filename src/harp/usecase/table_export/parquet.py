from __future__ import annotations

from .dto import (
    ExportTableToParquetDeps,
    ExportTableToParquetRequest,
    ExportTableToParquetResult,
)


def run_export_table_to_parquet_usecase(
    req: ExportTableToParquetRequest,
    deps: ExportTableToParquetDeps,
) -> ExportTableToParquetResult:
    if not req.source_table.strip():
        raise ValueError("source_table must not be empty")
    if not req.output_path.strip():
        raise ValueError("output_path must not be empty")
    if not req.compression.strip():
        raise ValueError("compression must not be empty")
    if deps.file_gateway.exists(req.output_path) and not req.overwrite:
        raise ValueError(f"output already exists; pass --overwrite: {req.output_path}")

    artifact = deps.parquet_exporter.export_table(
        source_table=req.source_table,
        output_path=req.output_path,
        where=req.where,
        compression=req.compression,
    )
    return ExportTableToParquetResult(
        source_table=req.source_table,
        output_path=artifact.output_path,
        row_count=artifact.row_count,
        file_size_bytes=artifact.file_size_bytes,
        compression=artifact.compression,
    )
