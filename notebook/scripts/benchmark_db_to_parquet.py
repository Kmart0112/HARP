from __future__ import annotations

import argparse
import os
import re
import resource
import sys
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from psycopg.rows import dict_row
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.runtime_settings import load_pipeline_runtime_config


DEFAULT_SQL = """
SELECT *
FROM mart.m_train_race_horse_past5
WHERE race_level BETWEEN 1 AND 3
  AND held_date >= :start_date
"""


@dataclass(frozen=True)
class BenchmarkResult:
    method: str
    elapsed_sec: float
    rows: int
    file_size_mb: float
    max_rss_mb: float
    output_path: Path
    coerced_decimal_values: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark DB -> parquet export methods.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default="",
        help="PostgreSQL URL. Defaults to HARP_DB_URL/.env.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2013-01-01",
        help="Query lower bound for held_date.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=200_000,
        help="Rows per chunk/fetch.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("notebook/tmp/benchmark_db_to_parquet"),
        help="Directory for benchmark outputs.",
    )
    parser.add_argument(
        "--compression",
        type=str,
        default="snappy",
        help="Parquet compression codec.",
    )
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=None,
        help="Optional .sql file. Must use :start_date bind if needed.",
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=("both", "pandas_concat", "psycopg_arrow_stream", "copy_csv_pyarrow"),
        default="both",
        help="Benchmark target method.",
    )
    parser.add_argument(
        "--schema-table",
        type=str,
        default="mart.m_train_race_horse_past5",
        help="Source table for DB-schema-driven Arrow column_types.",
    )
    return parser.parse_args()


def resolve_db_url(cli_db_url: str, *, default_db_url: str) -> str:
    db_url = cli_db_url.strip() or default_db_url
    if not db_url:
        raise ValueError("db-url is required.")
    return db_url


def normalize_psycopg_url(db_url: str) -> str:
    return (
        db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )


def to_psycopg_named_sql(sql_text: str) -> str:
    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql_text)


def mask_db_url(db_url: str) -> str:
    parts = urlsplit(db_url)
    if "@" not in parts.netloc:
        return db_url
    auth, host = parts.netloc.rsplit("@", 1)
    user = auth.split(":", 1)[0]
    safe_auth = user if user else "***"
    return urlunsplit((parts.scheme, f"{safe_auth}:***@{host}", parts.path, parts.query, parts.fragment))


def load_sql(sql_file: Path | None) -> str:
    if sql_file is None:
        return DEFAULT_SQL.strip()
    return sql_file.read_text(encoding="utf-8").strip()


def parse_schema_table(schema_table: str) -> tuple[str, str]:
    parts = [part.strip() for part in schema_table.split(".", 1)]
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"schema-table must be <schema>.<table>: {schema_table}")
    return parts[0], parts[1]


def build_copy_convert_options(
    *,
    engine: Engine,
    schema_table: str,
) -> pacsv.ConvertOptions:
    schema_name, table_name = parse_schema_table(schema_table)
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
        column_rows = list(rows)

    if not column_rows:
        raise ValueError(f"schema metadata not found for {schema_table}")

    column_types: dict[str, pa.DataType] = {}
    for row in column_rows:
        column_types[str(row.column_name)] = map_db_column_to_arrow_type(
            data_type=str(row.data_type),
            udt_name=str(row.udt_name),
            numeric_precision=row.numeric_precision,
            numeric_scale=row.numeric_scale,
        )

    return pacsv.ConvertOptions(
        column_types=column_types,
        true_values=["t", "true", "TRUE"],
        false_values=["f", "false", "FALSE"],
        strings_can_be_null=True,
        null_values=["", "NULL", "null"],
    )


def map_db_column_to_arrow_type(
    *,
    data_type: str,
    udt_name: str,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> pa.DataType:
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
    if data_type == "double precision":
        return pa.float64()
    if data_type == "numeric":
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


def max_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if os.uname().sysname == "Darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def prepare_output_path(output_dir: Path, method: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{method}.parquet"
    if output_path.exists():
        output_path.unlink()
    return output_path


def normalize_arrow_batch(batch_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    coerced = 0
    normalized_rows: list[dict[str, object]] = []
    for row in batch_rows:
        normalized_row: dict[str, object] = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                normalized_row[key] = str(value)
                coerced += 1
                continue
            normalized_row[key] = value
        normalized_rows.append(normalized_row)
    return normalized_rows, coerced


def promote_columns_to_string(
    batch_rows: list[dict[str, object]],
    columns: set[str],
) -> list[dict[str, object]]:
    if not columns:
        return batch_rows
    promoted_rows: list[dict[str, object]] = []
    for row in batch_rows:
        promoted_row: dict[str, object] = {}
        for key, value in row.items():
            if key in columns and value is not None:
                promoted_row[key] = str(value)
            else:
                promoted_row[key] = value
        promoted_rows.append(promoted_row)
    return promoted_rows


def run_pandas_export(
    *,
    db_url: str,
    sql_text: str,
    start_date: str,
    chunk_size: int,
    output_dir: Path,
    compression: str,
) -> BenchmarkResult:
    output_path = prepare_output_path(output_dir, "pandas_concat")
    started = time.perf_counter()
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=1800)

    with engine.connect().execution_options(stream_results=True) as conn:
        chunks = pd.read_sql_query(
            text(sql_text),
            conn,
            params={"start_date": start_date},
            chunksize=chunk_size,
        )
        df = pd.concat(chunks, ignore_index=True)

    rows = int(len(df))
    df.to_parquet(output_path, engine="pyarrow", index=False, compression=compression)
    elapsed_sec = time.perf_counter() - started
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    return BenchmarkResult(
        method="pandas_concat",
        elapsed_sec=elapsed_sec,
        rows=rows,
        file_size_mb=file_size_mb,
        max_rss_mb=max_rss_mb(),
        output_path=output_path,
    )


def run_psycopg_arrow_stream_export(
    *,
    db_url: str,
    sql_text: str,
    start_date: str,
    chunk_size: int,
    output_dir: Path,
    compression: str,
) -> BenchmarkResult:
    output_path = prepare_output_path(output_dir, "psycopg_arrow_stream")
    started = time.perf_counter()
    rows = 0
    writer: pq.ParquetWriter | None = None
    coerced_decimal_values = 0
    string_promoted_columns: set[str] = set()

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor(name="harp_export_benchmark") as cur:
            cur.itersize = chunk_size
            cur.execute(to_psycopg_named_sql(sql_text), {"start_date": start_date})

            while True:
                batch_rows = cur.fetchmany(chunk_size)
                if not batch_rows:
                    break
                batch_rows, batch_coerced = normalize_arrow_batch(batch_rows)
                coerced_decimal_values += batch_coerced
                batch_rows = promote_columns_to_string(batch_rows, string_promoted_columns)
                table = pa.Table.from_pylist(batch_rows)
                if writer is None:
                    null_columns = {
                        field.name for field in table.schema
                        if pa.types.is_null(field.type)
                    }
                    if null_columns:
                        string_promoted_columns.update(null_columns)
                        batch_rows = promote_columns_to_string(batch_rows, null_columns)
                        table = pa.Table.from_pylist(batch_rows)
                    writer = pq.ParquetWriter(
                        output_path,
                        table.schema,
                        compression=compression,
                        use_dictionary=True,
                    )
                else:
                    table = table.cast(writer.schema, safe=False)
                writer.write_table(table)
                rows += table.num_rows

    if writer is None:
        empty_table = pa.table({})
        pq.write_table(empty_table, output_path, compression=compression)
    else:
        writer.close()

    elapsed_sec = time.perf_counter() - started
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    return BenchmarkResult(
        method="psycopg_arrow_stream",
        elapsed_sec=elapsed_sec,
        rows=rows,
        file_size_mb=file_size_mb,
        max_rss_mb=max_rss_mb(),
        output_path=output_path,
        coerced_decimal_values=coerced_decimal_values,
    )


def run_copy_csv_pyarrow_export(
    *,
    db_url: str,
    sql_text: str,
    start_date: str,
    chunk_size: int,
    output_dir: Path,
    compression: str,
    schema_table: str,
) -> BenchmarkResult:
    output_path = prepare_output_path(output_dir, "copy_csv_pyarrow")
    started = time.perf_counter()
    rows = 0
    temp_csv_path: Path | None = None
    engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=1800)
    convert_options = build_copy_convert_options(engine=engine, schema_table=schema_table)

    copy_sql = (
        "COPY ("
        + to_psycopg_named_sql(sql_text)
        + ") TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".csv",
        dir=output_dir,
        delete=False,
    ) as temp_file:
        temp_csv_path = Path(temp_file.name)

        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                with cur.copy(copy_sql, {"start_date": start_date}) as copy:
                    for data in copy:
                        payload = data.encode("utf-8") if isinstance(data, str) else data
                        temp_file.write(payload)

    writer: pq.ParquetWriter | None = None
    try:
        open_csv = pacsv.open_csv(
            temp_csv_path,
            read_options=pacsv.ReadOptions(
                use_threads=True,
                block_size=max(1 << 20, chunk_size * 256),
            ),
            convert_options=convert_options,
        )
        while True:
            batch = open_csv.read_next_batch()
            if batch is None:
                break
            table = pa.Table.from_batches([batch])
            if writer is None:
                writer = pq.ParquetWriter(
                    output_path,
                    table.schema,
                    compression=compression,
                    use_dictionary=True,
                )
            writer.write_table(table)
            rows += batch.num_rows
    except StopIteration:
        pass
    finally:
        if writer is not None:
            writer.close()
        if temp_csv_path is not None and temp_csv_path.exists():
            temp_csv_path.unlink()

    if writer is None:
        pq.write_table(pa.table({}), output_path, compression=compression)

    elapsed_sec = time.perf_counter() - started
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    return BenchmarkResult(
        method="copy_csv_pyarrow",
        elapsed_sec=elapsed_sec,
        rows=rows,
        file_size_mb=file_size_mb,
        max_rss_mb=max_rss_mb(),
        output_path=output_path,
    )


def print_result(result: BenchmarkResult) -> None:
    print(
        " ".join(
            [
                f"method={result.method}",
                f"rows={result.rows}",
                f"elapsed_sec={result.elapsed_sec:.3f}",
                f"file_size_mb={result.file_size_mb:.2f}",
                f"max_rss_mb={result.max_rss_mb:.2f}",
                f"coerced_decimal_values={result.coerced_decimal_values}",
                f"output={result.output_path}",
            ]
        )
    )


def main() -> None:
    args = parse_args()
    runtime_config = load_pipeline_runtime_config()
    db_url = resolve_db_url(args.db_url, default_db_url=runtime_config.database.db_url)
    sql_text = load_sql(args.sql_file)

    print(f"db_url={mask_db_url(db_url)}")
    print(f"start_date={args.start_date}")
    print(f"chunk_size={args.chunk_size}")
    print(f"compression={args.compression}")
    print(f"output_dir={args.output_dir}")
    print(f"schema_table={args.schema_table}")

    pandas_result: BenchmarkResult | None = None
    stream_result: BenchmarkResult | None = None

    if args.method in {"both", "pandas_concat"}:
        pandas_result = run_pandas_export(
            db_url=db_url,
            sql_text=sql_text,
            start_date=args.start_date,
            chunk_size=args.chunk_size,
            output_dir=args.output_dir,
            compression=args.compression,
        )
        print_result(pandas_result)

    if args.method in {"both", "psycopg_arrow_stream"}:
        stream_result = run_psycopg_arrow_stream_export(
            db_url=normalize_psycopg_url(db_url),
            sql_text=sql_text,
            start_date=args.start_date,
            chunk_size=args.chunk_size,
            output_dir=args.output_dir,
            compression=args.compression,
        )
        print_result(stream_result)

    if args.method in {"both", "copy_csv_pyarrow"}:
        copy_result = run_copy_csv_pyarrow_export(
            db_url=normalize_psycopg_url(db_url),
            sql_text=sql_text,
            start_date=args.start_date,
            chunk_size=args.chunk_size,
            output_dir=args.output_dir,
            compression=args.compression,
            schema_table=args.schema_table,
        )
        print_result(copy_result)

    if pandas_result is not None and stream_result is not None:
        if pandas_result.rows != stream_result.rows:
            raise RuntimeError(
                "row count mismatch: "
                f"pandas={pandas_result.rows} stream={stream_result.rows}"
            )

        speedup = pandas_result.elapsed_sec / stream_result.elapsed_sec if stream_result.elapsed_sec else float("inf")
        print(f"speedup_vs_pandas={speedup:.3f}")


if __name__ == "__main__":
    main()
