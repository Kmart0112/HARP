from __future__ import annotations

import argparse

from harp.controllers import ExportTableToParquetCommand, TableParquetExportController
from harp.config import DatabaseConfig
from pipeline.jobs._where_parser import parse_where_args
from pipeline.runtime_settings import load_table_export_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a PostgreSQL table to parquet via COPY CSV + pyarrow.",
    )
    parser.add_argument(
        "--source-table",
        type=str,
        default=None,
        help="Source table in <schema>.<table> form.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Target parquet path.",
    )
    parser.add_argument(
        "--where",
        action="append",
        default=None,
        help="Optional filter in key=value form. Supports __gte/__lte/... operators.",
    )
    parser.add_argument(
        "--compression",
        type=str,
        default="snappy",
        help="Parquet compression codec.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default="",
        help="PostgreSQL URL. Defaults to HARP_DB_URL/.env.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output parquet.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success summary output.",
    )
    return parser.parse_args()


def _print_summary(result) -> None:  # noqa: ANN001
    size_mb = result.file_size_bytes / (1024 * 1024)
    print(
        f"status=exported source_table={result.source_table} output={result.output_path} "
        f"rows={result.row_count} file_size_mb={size_mb:.2f} compression={result.compression}"
    )


def main() -> None:
    args = parse_args()
    explicit_db_url = str(args.db_url).strip()
    source_table = "" if args.source_table is None else str(args.source_table).strip()
    if not source_table or not explicit_db_url:
        config = load_table_export_runtime_config()
        source_table = source_table or config.source_table
        explicit_db_url = explicit_db_url or config.db_url

    command = ExportTableToParquetCommand(
        source_table=source_table,
        output_path=args.output,
        where=parse_where_args(args.where),
        compression=args.compression,
        overwrite=bool(args.overwrite),
        quiet=bool(args.quiet),
    )
    try:
        result = TableParquetExportController(DatabaseConfig(db_url=explicit_db_url)).run(command)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(2) from exc

    if not args.quiet:
        _print_summary(result)


if __name__ == "__main__":
    main()
