"""Consumer-owned query and result types for training and prediction Ports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from .odds import (
    OddsBatch,
    OddsContractError,
    OddsPolicy,
    normalize_entry_keys,
    utc_timestamp,
)


@dataclass(frozen=True)
class RaceInputQuery:
    from_date: str
    to_date: str
    feature_names: tuple[str, ...]
    odds_policy: OddsPolicy
    target_names: tuple[str, ...] = ()
    max_races: int | None = None
    filters: dict[str, object] = field(default_factory=dict)
    categorical_features: tuple[str, ...] = ()

    def __post_init__(self):
        if date.fromisoformat(self.from_date) > date.fromisoformat(self.to_date):
            raise OddsContractError("from_date must not exceed to_date")
        if self.max_races is not None and self.max_races < 1:
            raise OddsContractError("max_races must be positive")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise OddsContractError("duplicate feature names")
        if not set(self.categorical_features).issubset(self.feature_names):
            raise OddsContractError("categorical fields must be requested features")


class RaceInputs:
    """A coherent input batch; odds and rows have exactly the same entry set."""
    def __init__(self, frame: pd.DataFrame, odds: OddsBatch, source_revision: str,
                 captured_at: datetime | None = None):
        self._frame = normalize_entry_keys(frame, name="RaceInputs")
        if "scheduled_start_at" in self._frame:
            self._frame["scheduled_start_at"] = pd.Series([
                pd.NaT if pd.isna(value) else utc_timestamp(value, field="scheduled_start_at")
                for value in self._frame.scheduled_start_at
            ], dtype="datetime64[ns, UTC]")
        odds.align(self._frame)
        self._odds = odds
        self._source_revision = source_revision
        self._captured_at = utc_timestamp(captured_at, field="captured_at").to_pydatetime() if captured_at is not None else None

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)

    @property
    def odds(self) -> OddsBatch:
        return self._odds

    @property
    def source_revision(self) -> str:
        return self._source_revision

    @property
    def captured_at(self) -> datetime | None:
        return self._captured_at

    def validate_query(self, query: RaceInputQuery) -> None:
        if self.odds.policy != query.odds_policy:
            raise OddsContractError("provider returned a different odds policy")
        required = set(query.feature_names) - {"odds_tansho", "j_odds_tansho", "log_odds_tansho", "popularity", "popularity_ratio"}
        if not required.union(query.target_names).issubset(self.frame.columns):
            raise OddsContractError("provider omitted requested input fields")
        dates = pd.to_datetime(self.frame.held_date, errors="raise")
        if not dates.between(pd.Timestamp(query.from_date), pd.Timestamp(query.to_date)).all():
            raise OddsContractError("provider returned entries outside the requested dates")
