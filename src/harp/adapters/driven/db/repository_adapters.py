from __future__ import annotations

import pandas as pd

from harp.interface.ports import DataReadPort
from .data_read_adapter import PostgresDataReadAdapter
from .polars_data_read_adapter import PolarsToPandasDataReadAdapter, PostgresPolarsDataReadAdapter


class SqlInferenceRepositoryAdapter:
    def __init__(self, data_read_port: DataReadPort) -> None:
        self._data_read_port = data_read_port

    def load_recent_features(
        self,
        from_date: str | None,
        to_date: str | None,
        limit: int | None,
        mart_table: str,
    ) -> pd.DataFrame:
        where: dict[str, object] = {}
        if from_date is not None:
            where["held_date__gte"] = from_date
        if to_date is not None:
            where["held_date__lte"] = to_date

        return self._data_read_port.select(
            table=mart_table,
            where=where or None,
            order_by=["held_date DESC", "race_id DESC", "horse_number ASC"],
            limit=limit,
        )

    def load_odds(
        self,
        from_date: str | None = None,  # noqa: ARG002
        to_date: str | None = None,  # noqa: ARG002
    ) -> pd.DataFrame:
        # `core.fct_race_odds_result` currently has no held_date in this project, so range filters are ignored.
        return self._data_read_port.select(table="core.fct_race_odds_result")

    def load_race_info(
        self,
        from_date: str | None,
        to_date: str | None,
    ) -> pd.DataFrame:
        where: dict[str, object] = {}
        if from_date is not None:
            where["held_date__gte"] = from_date
        if to_date is not None:
            where["held_date__lte"] = to_date

        return self._data_read_port.select(
            table="core.race_info_wide",
            where=where or None,
        )


class SqlTrainingRepositoryAdapter:
    def __init__(self, data_read_port: DataReadPort) -> None:
        self._data_read_port = data_read_port

    def load_training_frame(
        self,
        max_year: int,
        limit: int | None,
        mart_table: str,
        where: dict[str, object] | None = None,
    ) -> pd.DataFrame:
        merged_where: dict[str, object] = {}
        if where:
            merged_where.update(where)
        merged_where["held_year__lte"] = int(max_year)
        return self._data_read_port.select(
            table=mart_table,
            where=merged_where,
            order_by=["held_date DESC", "race_id DESC", "horse_number ASC"],
            limit=limit,
        )


class PostgresInferenceRepositoryAdapter(SqlInferenceRepositoryAdapter):
    def __init__(self, *, db_url: str) -> None:
        super().__init__(PostgresDataReadAdapter(db_url=db_url))


class PostgresTrainingRepositoryAdapter(SqlTrainingRepositoryAdapter):
    def __init__(self, *, db_url: str) -> None:
        super().__init__(PostgresDataReadAdapter(db_url=db_url))


class PostgresPolarsInferenceRepositoryAdapter(SqlInferenceRepositoryAdapter):
    def __init__(self, *, db_url: str) -> None:
        super().__init__(
            PolarsToPandasDataReadAdapter(
                PostgresPolarsDataReadAdapter(db_url=db_url),
            )
        )


class PostgresPolarsTrainingRepositoryAdapter(SqlTrainingRepositoryAdapter):
    def __init__(self, *, db_url: str) -> None:
        super().__init__(
            PolarsToPandasDataReadAdapter(
                PostgresPolarsDataReadAdapter(db_url=db_url),
            )
        )
