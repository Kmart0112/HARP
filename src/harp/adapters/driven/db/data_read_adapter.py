from __future__ import annotations

import pandas as pd

from harp.shared.db import read_sql_df

from .sql_query_builder import normalize_order_item, validate_identifier, where_to_sql


class PostgresDataReadAdapter:
    def __init__(self, *, db_url: str) -> None:
        self._db_url = db_url

    def select(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
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

        return read_sql_df(sql=sql, params=params or None, db_url=self._db_url)

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
