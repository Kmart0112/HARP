from __future__ import annotations

import re
from typing import Any

import pandas as pd
import polars as pl
from sqlalchemy import literal
from sqlalchemy.dialects import postgresql

from harp.interface.ports import PolarsDataReadPort

from .sql_query_builder import normalize_order_item, validate_identifier, where_to_sql


_PARAM_PATTERN = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class PostgresPolarsDataReadAdapter:
    def __init__(self, *, db_url: str) -> None:
        self._db_url = _normalize_connectorx_url(db_url)

    def query(
        self,
        sql: str,
        params: dict[str, object] | None = None,
        partition_on: str | None = None,
        partition_range: tuple[int, int] | None = None,
        partition_num: int | None = None,
        schema_overrides: dict[str, pl.DataType] | None = None,
    ) -> pl.DataFrame:
        rendered_sql = _render_sql_params(sql, params or {})
        return pl.read_database_uri(
            rendered_sql,
            self._db_url,
            engine="connectorx",
            partition_on=partition_on,
            partition_range=partition_range,
            partition_num=partition_num,
            schema_overrides=schema_overrides,
        )

    def select(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
        partition_on: str | None = None,
        partition_range: tuple[int, int] | None = None,
        partition_num: int | None = None,
        schema_overrides: dict[str, pl.DataType] | None = None,
    ) -> pl.DataFrame:
        table_name = validate_identifier(table, kind="table")

        if columns:
            col_text = ", ".join(validate_identifier(c, kind="column") for c in columns)
        else:
            col_text = "*"

        where_sql, params = where_to_sql(where)
        sql = f"SELECT {col_text} FROM {table_name}{where_sql}"

        if order_by:
            order_text = ", ".join(normalize_order_item(x) for x in order_by)
            sql += f" ORDER BY {order_text}"

        if limit is not None:
            limit_n = int(limit)
            if limit_n <= 0:
                raise ValueError(f"limit must be positive: {limit}")
            sql += f" LIMIT {limit_n}"

        return self.query(
            sql,
            params=params or None,
            partition_on=partition_on,
            partition_range=partition_range,
            partition_num=partition_num,
            schema_overrides=schema_overrides,
        )

    def select_one(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        schema_overrides: dict[str, pl.DataType] | None = None,
    ) -> dict[str, object] | None:
        df = self.select(
            table=table,
            where=where,
            columns=columns,
            order_by=order_by,
            limit=1,
            schema_overrides=schema_overrides,
        )
        if df.is_empty():
            return None
        return dict(df.row(0, named=True))


class PolarsToPandasDataReadAdapter:
    def __init__(
        self,
        polars_data_read_port: PolarsDataReadPort,
        *,
        use_pyarrow_extension_array: bool = False,
    ) -> None:
        self._polars_data_read_port = polars_data_read_port
        self._use_pyarrow_extension_array = use_pyarrow_extension_array

    def select(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        df = self._polars_data_read_port.select(
            table=table,
            where=where,
            columns=columns,
            order_by=order_by,
            limit=limit,
        )
        return self._to_pandas(df)

    def select_one(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
    ) -> dict[str, object] | None:
        df = self.select(
            table=table,
            where=where,
            columns=columns,
            order_by=order_by,
            limit=1,
        )
        if df.empty:
            return None
        return {str(k): v for k, v in df.iloc[0].to_dict().items()}

    def _to_pandas(self, df: pl.DataFrame) -> pd.DataFrame:
        return df.to_pandas(
            use_pyarrow_extension_array=self._use_pyarrow_extension_array,
        )


def _render_sql_params(sql: str, params: dict[str, object]) -> str:
    if not params:
        return sql

    missing = {match.group(1) for match in _PARAM_PATTERN.finditer(sql)} - set(params)
    if missing:
        raise ValueError(f"SQL params missing values: {sorted(missing)}")

    return _PARAM_PATTERN.sub(lambda match: _literal_sql(params[match.group(1)]), sql)


def _literal_sql(value: object) -> str:
    compiled = literal(value).compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


def _normalize_connectorx_url(db_url: str) -> str:
    return (
        db_url.replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )
