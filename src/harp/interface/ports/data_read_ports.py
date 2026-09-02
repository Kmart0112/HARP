from __future__ import annotations

from typing import Protocol

import pandas as pd
import polars as pl


class DataReadPort(Protocol):
    def select(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        ...

    def select_one(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
    ) -> dict[str, object] | None:
        ...


class PolarsDataReadPort(Protocol):
    def query(
        self,
        sql: str,
        params: dict[str, object] | None = None,
        partition_on: str | None = None,
        partition_range: tuple[int, int] | None = None,
        partition_num: int | None = None,
        schema_overrides: dict[str, pl.DataType] | None = None,
    ) -> pl.DataFrame:
        ...

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
        ...

    def select_one(
        self,
        table: str,
        where: dict[str, object] | None = None,
        columns: list[str] | None = None,
        order_by: list[str] | None = None,
        schema_overrides: dict[str, pl.DataType] | None = None,
    ) -> dict[str, object] | None:
        ...
