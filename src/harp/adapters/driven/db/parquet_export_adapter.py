from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from sqlalchemy import text

from harp.interface.ports import TableParquetExportArtifact
from harp.shared.db import get_engine

from .sql_query_builder import validate_identifier, where_to_sql

_DEFAULT_CSV_BLOCK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True)
class CopyCsvArrowSchema:
    column_types: dict[str, pa.DataType]
    schema: pa.Schema


def normalize_psycopg_url(db_url: str) -> str:
    return (
        db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )


def to_psycopg_named_sql(sql_text: str) -> str:
    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql_text)


def parse_schema_table(source_table: str) -> tuple[str, str]:
    schema_name, table_name = source_table.split(".", 1)
    return (
        validate_identifier(schema_name, kind="table schema"),
        validate_identifier(table_name, kind="table name"),
    )


def map_db_column_to_arrow_type(
    *,
    data_type: str,
    udt_name: str,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> pa.DataType:
    del numeric_precision, numeric_scale

    if data_type == "boolean":
        return pa.bool_()
    if data_type == "smallint":
        return pa.int16()
    if data_type == "integer":
        return pa.int32()
    if data_type == "bigint":
        return pa.int64()
    if data_type == "real":
        return pa.float32()
    if data_type in {"double precision", "numeric"}:
        return pa.float64()
    if data_type == "date":
        return pa.date32()
    if data_type == "timestamp with time zone":
        return pa.timestamp("ms", tz="UTC")
    if data_type == "timestamp without time zone":
        return pa.timestamp("ms")
    if data_type in {"text", "character varying", "character", "uuid"}:
        return pa.string()
    if udt_name in {"json", "jsonb"}:
        return pa.string()
    return pa.string()


def build_copy_arrow_schema(*, db_url: str, source_table: str) -> CopyCsvArrowSchema:
    schema_name, table_name = parse_schema_table(source_table)
    engine = get_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    column_name,
                    data_type,
                    udt_name,
                    numeric_precision,
                    numeric_scale
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                ORDER BY ordinal_position
                """
            ),
            {
                "schema_name": schema_name,
                "table_name": table_name,
            },
        )
        column_rows = list(rows.mappings())

    if not column_rows:
        raise ValueError(f"schema metadata not found for {source_table}")

    fields: list[pa.Field] = []
    for row in column_rows:
        arrow_type = map_db_column_to_arrow_type(
            data_type=str(row["data_type"]),
            udt_name=str(row["udt_name"]),
            numeric_precision=row["numeric_precision"],
            numeric_scale=row["numeric_scale"],
        )
        fields.append(pa.field(str(row["column_name"]), arrow_type, nullable=True))

    schema = pa.schema(fields)
    return CopyCsvArrowSchema(
        column_types={field.name: field.type for field in fields},
        schema=schema,
    )


def build_copy_convert_options(schema_config: CopyCsvArrowSchema) -> pacsv.ConvertOptions:
    return pacsv.ConvertOptions(
        column_types=schema_config.column_types,
        true_values=["t", "true", "TRUE"],
        false_values=["f", "false", "FALSE"],
        strings_can_be_null=True,
        null_values=["", "NULL", "null"],
    )


def build_select_star_sql(
    *,
    source_table: str,
    where: dict[str, object] | None,
) -> tuple[str, dict[str, object]]:
    table_name = validate_identifier(source_table, kind="table")
    where_sql, params = where_to_sql(where)
    return f"SELECT * FROM {table_name}{where_sql}", params


class PostgresCopyCsvParquetExportAdapter:
    def __init__(self, *, db_url: str) -> None:
        self._db_url = db_url

    def export_table(
        self,
        *,
        source_table: str,
        output_path: str,
        where: dict[str, object] | None = None,
        compression: str = "snappy",
    ) -> TableParquetExportArtifact:
        sql_text, params = build_select_star_sql(source_table=source_table, where=where)
        schema_config = build_copy_arrow_schema(db_url=self._db_url, source_table=source_table)
        convert_options = build_copy_convert_options(schema_config)
        parquet_path = Path(output_path)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        copy_sql = (
            "COPY ("
            + to_psycopg_named_sql(sql_text)
            + ") TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
        )

        temp_csv_path: Path | None = None
        writer: pq.ParquetWriter | None = None
        row_count = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".csv",
                dir=parquet_path.parent,
                delete=False,
            ) as temp_file:
                temp_csv_path = Path(temp_file.name)
                with psycopg.connect(normalize_psycopg_url(self._db_url)) as conn:
                    with conn.cursor() as cur:
                        with cur.copy(copy_sql, params) as copy:
                            for data in copy:
                                payload = data.encode("utf-8") if isinstance(data, str) else data
                                temp_file.write(payload)

            open_csv = pacsv.open_csv(
                temp_csv_path,
                read_options=pacsv.ReadOptions(
                    use_threads=True,
                    block_size=_DEFAULT_CSV_BLOCK_SIZE,
                ),
                convert_options=convert_options,
            )
            try:
                while True:
                    batch = open_csv.read_next_batch()
                    if batch is None:
                        break
                    table = pa.Table.from_batches([batch], schema=schema_config.schema)
                    if writer is None:
                        writer = pq.ParquetWriter(
                            parquet_path,
                            schema_config.schema,
                            compression=compression,
                            use_dictionary=True,
                        )
                    writer.write_table(table)
                    row_count += batch.num_rows
            except StopIteration:
                pass

            if writer is None:
                pq.write_table(
                    pa.Table.from_batches([], schema=schema_config.schema),
                    parquet_path,
                    compression=compression,
                )
            else:
                writer.close()
                writer = None
        finally:
            if writer is not None:
                writer.close()
            if temp_csv_path is not None and temp_csv_path.exists():
                temp_csv_path.unlink()

        return TableParquetExportArtifact(
            output_path=str(parquet_path),
            row_count=row_count,
            file_size_bytes=parquet_path.stat().st_size,
            compression=compression,
        )
