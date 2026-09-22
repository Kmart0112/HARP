"""Storage-independent, point-in-time single-horse odds contract.

No database column names or I/O belong here. Prices are decimal payout multiples;
unavailable markets remain observable instead of dropping their entrants.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal

import numpy as np
import pandas as pd

ODDS_CONTRACT_VERSION = "1.0"
ENTRY_KEY = ["race_id", "horse_number"]
QUOTE_COLUMNS = [*ENTRY_KEY, "win_odds", "place_low", "place_high",
                 "win_popularity", "published_at", "available_at"]
ODDS_FEATURE_NAMES = frozenset({"odds_tansho", "j_odds_tansho", "log_odds_tansho",
                                "popularity", "popularity_ratio"})


class OddsContractError(ValueError):
    """The provider cannot satisfy the declared logical data contract."""


def utc_timestamp(value: object, *, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise OddsContractError(f"{field}: invalid timestamp") from exc
    if pd.isna(result) or result.tzinfo is None:
        raise OddsContractError(f"{field}: timezone-aware timestamp required")
    return result.tz_convert("UTC")


def require_columns(frame: pd.DataFrame, columns, *, name: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise OddsContractError(f"{name}: missing columns {missing}")
    if frame.columns.duplicated().any():
        raise OddsContractError(f"{name}: duplicate column names")


def normalize_entry_keys(frame: pd.DataFrame, *, name: str, unique: bool = True) -> pd.DataFrame:
    require_columns(frame, ENTRY_KEY, name=name)
    out = frame.copy().reset_index(drop=True)
    if out[ENTRY_KEY].isna().any().any():
        raise OddsContractError(f"{name}: null entry key")
    # A 16-digit race identifier must never pass through floating point.
    if out.race_id.map(lambda value: isinstance(value, (float, np.floating))).any():
        raise OddsContractError(f"{name}: floating-point race_id is unsafe")
    out["race_id"] = out.race_id.astype(str)
    if out.race_id.str.strip().eq("").any():
        raise OddsContractError(f"{name}: empty race_id")
    try:
        numbers = pd.to_numeric(out.horse_number, errors="raise")
    except (ValueError, TypeError) as exc:
        raise OddsContractError(f"{name}: invalid horse_number") from exc
    if ((numbers < 1) | (numbers % 1 != 0) | ~np.isfinite(numbers)).any():
        raise OddsContractError(f"{name}: horse_number must be a positive integer")
    out["horse_number"] = numbers.astype("int64")
    if unique and out.duplicated(ENTRY_KEY).any():
        raise OddsContractError(f"{name}: duplicate entry key")
    return out


@dataclass(frozen=True)
class OddsPolicy:
    mode: Literal["latest_before", "pre_start"]
    max_age_seconds: float
    as_of: datetime | None = None
    minutes_before_start: int = 10
    require_availability: bool = False

    def __post_init__(self):
        if self.mode not in {"latest_before", "pre_start"}:
            raise OddsContractError(f"unsupported odds policy: {self.mode}")
        if not np.isfinite(self.max_age_seconds) or self.max_age_seconds < 0:
            raise OddsContractError("max_age_seconds must be finite and nonnegative")
        if self.minutes_before_start < 0:
            raise OddsContractError("minutes_before_start must be nonnegative")
        if not isinstance(self.minutes_before_start, int):
            raise OddsContractError("minutes_before_start must be an integer")
        if self.mode == "latest_before":
            object.__setattr__(self, "as_of", utc_timestamp(self.as_of, field="as_of").to_pydatetime())
        elif self.as_of is not None:
            raise OddsContractError("pre_start must not have a global as_of")

    @classmethod
    def latest(cls, as_of, max_age_seconds, *, require_availability=False):
        return cls("latest_before", max_age_seconds, as_of, require_availability=require_availability)

    @classmethod
    def pre_start(cls, *, minutes=10, max_age_seconds, require_availability=False):
        return cls("pre_start", max_age_seconds, minutes_before_start=minutes,
                   require_availability=require_availability)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "max_age_seconds": self.max_age_seconds,
                "as_of": self.as_of.isoformat() if self.as_of else None,
                "minutes_before_start": self.minutes_before_start,
                "require_availability": self.require_availability}


class OddsBatch:
    """Validated quotes aligned to all requested entrants; returns defensive copies."""

    def __init__(self, frame: pd.DataFrame, *, policy: OddsPolicy,
                 availability_basis: str, contract_version: str = ODDS_CONTRACT_VERSION):
        if contract_version != ODDS_CONTRACT_VERSION:
            raise OddsContractError(f"unsupported odds contract: {contract_version}")
        require_columns(frame, [*QUOTE_COLUMNS, "cutoff_at", "quote_id", "win_status", "place_status"],
                        name="OddsBatch")
        self._frame = normalize_entry_keys(frame, name="OddsBatch")
        if availability_basis not in {"publication_time", "availability_time", "mixed"}:
            raise OddsContractError("invalid availability basis")
        for name in ["published_at", "available_at", "cutoff_at"]:
            self._frame[name] = _times(self._frame[name], field=name)
        if policy.mode == "latest_before" and self._frame.cutoff_at.isna().any():
            raise OddsContractError("missing global quote cutoff")
        if self._frame.published_at.gt(self._frame.cutoff_at).any() or self._frame.available_at.gt(self._frame.cutoff_at).any():
            raise OddsContractError("selected quote is after cutoff")
        if policy.mode == "latest_before" and not self._frame.cutoff_at.eq(pd.Timestamp(policy.as_of)).all():
            raise OddsContractError("selected quote cutoff differs from policy")
        for market in ["win", "place"]:
            if not self._frame[f"{market}_status"].eq(_market_status(self._frame, policy, market)).all():
                raise OddsContractError("quote status contradicts its prices or time")
        for _, row in self._frame.iterrows():
            actual = row.quote_id if pd.notna(row.quote_id) else None
            if actual != _quote_id(row):
                raise OddsContractError("quote identity contradicts its content")
        self.policy = policy
        self.availability_basis = availability_basis
        self.contract_version = contract_version

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)

    def align(self, entries: pd.DataFrame) -> pd.DataFrame:
        keys = normalize_entry_keys(entries[ENTRY_KEY], name="odds alignment")
        aligned = keys.merge(self._frame, on=ENTRY_KEY, how="left", validate="one_to_one", indicator=True)
        if aligned._merge.ne("both").any() or len(aligned) != len(self._frame):
            raise OddsContractError("odds alignment: entry set differs")
        return aligned.drop(columns="_merge")


def _times(series: pd.Series, *, field: str) -> pd.Series:
    values = [pd.NaT if pd.isna(value) else utc_timestamp(value, field=field) for value in series]
    return pd.Series(values, index=series.index, dtype="datetime64[ns, UTC]")


def _quote_id(row: pd.Series) -> str | None:
    if pd.isna(row.published_at):
        return None
    values = []
    for name in QUOTE_COLUMNS:
        value = row[name]
        if pd.isna(value):
            value = None
        elif isinstance(value, (pd.Timestamp, datetime)):
            value = value.isoformat()
        elif isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not np.isfinite(value):
            value = str(value)
        values.append(value)
    return sha256(json.dumps(values, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _market_status(frame, policy, market):
    absent = frame.published_at.isna()
    stale = (frame.cutoff_at - frame.published_at).dt.total_seconds().gt(policy.max_age_seconds)
    if market == "win":
        valid = np.isfinite(frame.win_odds) & frame.win_odds.ge(1)
        missing = frame.win_odds.isna()
    else:
        valid = (np.isfinite(frame.place_low) & np.isfinite(frame.place_high)
                 & frame.place_low.ge(1) & frame.place_high.ge(frame.place_low))
        missing = frame.place_low.isna() | frame.place_high.isna()
    return np.select([frame.cutoff_at.isna(), absent, stale, missing, valid],
                     ["unknown_cutoff", "missing", "stale", "unavailable", "available"], default="invalid")


def select_odds(entries: pd.DataFrame, quotes: pd.DataFrame, policy: OddsPolicy) -> OddsBatch:
    """Select newest known row before each cutoff, then assess market usability.

    Invalid latest prices deliberately do not fall back to older valid prices.
    Exact duplicate source deliveries are idempotent; conflicting revisions with
    identical publication/availability keys are a contract error.
    """
    target = normalize_entry_keys(entries, name="entries")
    require_columns(quotes, QUOTE_COLUMNS, name="quotes")
    source = normalize_entry_keys(quotes[QUOTE_COLUMNS], name="quotes", unique=False)
    if policy.mode == "pre_start":
        require_columns(target, ["scheduled_start_at"], name="entries")
        start = _times(target.scheduled_start_at, field="scheduled_start_at")
        target["cutoff_at"] = start - pd.Timedelta(minutes=policy.minutes_before_start)
    else:
        target["cutoff_at"] = pd.Timestamp(policy.as_of)
    for name in ["published_at", "available_at"]:
        source[name] = _times(source[name], field=name)
    for name in ["win_odds", "place_low", "place_high", "win_popularity"]:
        try:
            source[name] = pd.to_numeric(source[name], errors="raise").astype(float)
        except (ValueError, TypeError) as exc:
            raise OddsContractError(f"{name}: nonnumeric value") from exc
    source = source.merge(target[[*ENTRY_KEY, "cutoff_at"]], on=ENTRY_KEY, how="inner", validate="many_to_one")
    if (source.published_at.isna() & source[["win_odds", "place_low", "place_high"]].notna().any(axis=1)).any():
        raise OddsContractError("quote has prices but unknown publication time")
    if source.available_at.lt(source.published_at).any():
        raise OddsContractError("quote availability precedes publication")
    source = source.loc[source.published_at.le(source.cutoff_at)].copy()
    if policy.require_availability and source.available_at.isna().any():
        raise OddsContractError("available_at is required for availability-based replay")
    source = source.loc[source.available_at.isna() | source.available_at.le(source.cutoff_at)].copy()
    known = source.available_at.notna()
    basis = "availability_time" if len(source) and known.all() else "mixed" if known.any() else "publication_time"
    identity = [*ENTRY_KEY, "published_at", "available_at"]
    source = source.drop_duplicates()
    if source.duplicated(identity).any():
        raise OddsContractError("conflicting quote revisions")
    latest = source.sort_values(["published_at", "available_at"], na_position="first").drop_duplicates(ENTRY_KEY, keep="last")
    result = target[[*ENTRY_KEY, "cutoff_at"]].merge(latest.drop(columns="cutoff_at"), on=ENTRY_KEY,
                                                    how="left", validate="one_to_one")
    for market in ["win", "place"]:
        result[f"{market}_status"] = _market_status(result, policy, market)
    result["quote_id"] = result.apply(_quote_id, axis=1) if len(result) else pd.Series(dtype=object)
    return OddsBatch(result, policy=policy, availability_basis=basis)


def assemble_odds_features(features: pd.DataFrame, odds: OddsBatch) -> pd.DataFrame:
    """Project semantic odds into the stable model feature vocabulary once."""
    out = normalize_entry_keys(features, name="features")
    aligned = odds.align(out)
    win = aligned.win_odds.where(aligned.win_status.eq("available"))
    out["odds_tansho"] = win.to_numpy()
    out["j_odds_tansho"] = win.to_numpy()  # Existing artifact vocabulary, not a DB lookup.
    out["log_odds_tansho"] = np.log(win).to_numpy()
    popularity = aligned.win_popularity
    fresh = (aligned.published_at.notna() & aligned.cutoff_at.notna()
             & (aligned.cutoff_at - aligned.published_at).dt.total_seconds().le(odds.policy.max_age_seconds))
    valid_popularity = np.isfinite(popularity) & popularity.ge(1) & popularity.mod(1).eq(0)
    out["popularity"] = popularity.where(fresh & valid_popularity).to_numpy()
    if "num_starters" in out:
        counts = pd.to_numeric(out.num_starters, errors="raise").replace(0, np.nan)
        out["popularity_ratio"] = out.popularity / counts
    return out


def odds_features_available(features: pd.DataFrame, feature_names) -> pd.Series:
    required = sorted(set(feature_names) & ODDS_FEATURE_NAMES)
    if not required:
        return pd.Series(True, index=features.index)
    require_columns(features, required, name="odds features")
    return pd.Series(np.isfinite(features[required].to_numpy(dtype=float)).all(axis=1), index=features.index)
