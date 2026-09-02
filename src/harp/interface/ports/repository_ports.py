from __future__ import annotations

from typing import Protocol

import pandas as pd


class InferenceRepositoryPort(Protocol):
    def load_recent_features(
        self,
        from_date: str | None,
        to_date: str | None,
        limit: int | None,
        mart_table: str,
    ) -> pd.DataFrame:
        ...

    def load_odds(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        ...

    def load_race_info(
        self,
        from_date: str | None,
        to_date: str | None,
    ) -> pd.DataFrame:
        ...


class TrainingRepositoryPort(Protocol):
    def load_training_frame(
        self,
        max_year: int,
        limit: int | None,
        mart_table: str,
        where: dict[str, object] | None = None,
    ) -> pd.DataFrame:
        ...

