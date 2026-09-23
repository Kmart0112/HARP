"""Longitudinal NN inputs, kept separate from current-race targets.

History is a shared, complete prefix per horse, not a target-by-history join.
Only rows numbered at or below an entry's history_end_no may feed that entry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, UTC
from numbers import Integral, Real
import re

import numpy as np
import pandas as pd


NN_INPUT_VERSION = 1
ENTRY_KEY = ("race_id", "kettonum")
ENTRY_METADATA = (*ENTRY_KEY, "held_date", "horse_number", "history_end_no",
                  "last_history_race_id", "last_history_held_date",
                  "days_since_last_run", "active_entrant_count")
HISTORY_METADATA = (*ENTRY_KEY, "held_date", "run_no")
STATS_FLAGS = tuple(f"{entity}_stats_missing" for entity in
                    ("jockey", "trainer", "breeder", "sire", "dam", "damsire"))
STATS_METADATA = ("monthly_stats_cutoff", "yearly_stats_cutoff", *STATS_FLAGS)
_STATS_CUTOFF_GROUPS = {
    "monthly_stats_cutoff": (("jockey", "sire", "dam", "damsire"),
                             ("jockey_", "sire_", "dam_", "damsire_", "same_cluster_sire_")),
    "yearly_stats_cutoff": (("trainer", "breeder"), ("trainer_", "breeder_")),
}
TARGET_COLUMNS = ("result_order", "is_win", "is_place")
_RESULT_FIELDS = frozenset((*TARGET_COLUMNS, "time_sec", "time_diff", "agari3f",
                            "rank_1c", "rank_2c", "rank_3c", "rank_4c",
                            "running_style_cd", "result_status_code"))
_IDENTITIES = frozenset(("jockey_cd", "trainer_cd", "breeder_cd", "sire_id", "dam_id",
                         "damsire_id", "horse_name", "jockey_name", "trainer_name"))


class NnInputContractError(ValueError):
    """An input cannot be safely interpreted under the NN contract."""


@dataclass(frozen=True)
class NnFeatureField:
    name: str
    kind: str  # numeric or categorical; conversion does not fit a preprocessor.

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name) or self.kind not in {"numeric", "categorical"}:
            raise NnInputContractError("invalid feature field")


@dataclass(frozen=True)
class NnFeatureContract:
    pre_race: tuple[NnFeatureField, ...]
    history_results: tuple[NnFeatureField, ...]
    version: int = NN_INPUT_VERSION

    def __post_init__(self):
        object.__setattr__(self, "pre_race", tuple(self.pre_race))
        object.__setattr__(self, "history_results", tuple(self.history_results))
        if type(self.version) is not int or self.version != NN_INPUT_VERSION:
            raise NnInputContractError("unsupported NN input contract version")
        names = [field.name for field in (*self.pre_race, *self.history_results)]
        if not self.pre_race or len(set(names)) != len(names):
            raise NnInputContractError("empty or duplicate feature contract")
        reserved = set(ENTRY_METADATA + HISTORY_METADATA + STATS_METADATA) - {"horse_number"}
        if set(names) & (_IDENTITIES | reserved) or any(name.endswith("_id") for name in names):
            raise NnInputContractError("identity or management field cannot be a feature")
        if any("odds" in name or "popularity" in name or name in {"ijyo_cd", "is_scratched"} for name in names):
            raise NnInputContractError("odds or lifecycle field cannot be an NN feature")
        if set(self.pre_race_names) & _RESULT_FIELDS:
            raise NnInputContractError("post-race fields cannot be current features")
        if not set(self.history_result_names) <= _RESULT_FIELDS:
            raise NnInputContractError("unsupported historical result field")

    @property
    def pre_race_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.pre_race)

    @property
    def history_result_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.history_results)


@dataclass(frozen=True)
class NnInputQuery:
    from_date: str
    to_date: str
    feature_names: tuple[str, ...]
    history_result_names: tuple[str, ...] = ()
    max_races: int | None = None

    def __post_init__(self):
        try:
            if date.fromisoformat(self.from_date) > date.fromisoformat(self.to_date):
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise NnInputContractError("invalid NN input date range") from exc
        for attr in ("feature_names", "history_result_names"):
            names = tuple(getattr(self, attr))
            if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
                raise NnInputContractError("invalid or duplicate requested feature names")
            object.__setattr__(self, attr, names)
        if self.max_races is not None and (isinstance(self.max_races, bool)
                or not isinstance(self.max_races, Integral) or self.max_races < 1):
            raise NnInputContractError("max_races must be a positive integer")
        if self.max_races is not None:
            object.__setattr__(self, "max_races", int(self.max_races))

    def validate_contract(self, contract: NnFeatureContract) -> None:
        if not set(self.feature_names) <= set(contract.pre_race_names):
            raise NnInputContractError("requested current feature is not allowed by the input contract")
        if not set(self.history_result_names) <= set(contract.history_result_names):
            raise NnInputContractError("requested history result is not allowed by the input contract")


def _identifier(value):
    if pd.isna(value):
        return pd.NA
    if isinstance(value, bool) or not isinstance(value, (str, Integral)):
        raise NnInputContractError("IDs must be strings or integers, never floats")
    result = str(value)
    if not result or result != result.strip():
        raise NnInputContractError("invalid empty or padded ID")
    return result


def _ids(values):
    # Series.map on nullable Int64 may first convert through float64, losing IDs.
    return pd.Series([_identifier(value) for value in values.array], index=values.index, dtype="string")


def _dates(values, *, nullable=False):
    try:
        result = pd.to_datetime(values, errors="raise")
        if result.dt.tz is not None or (not nullable and result.isna().any()):
            raise ValueError
        if not result.dropna().eq(result.dropna().dt.normalize()).all():
            raise ValueError
        return result.astype("datetime64[ns]")
    except (ValueError, TypeError, AttributeError) as exc:
        raise NnInputContractError("invalid event date") from exc


def _numbers(values, *, integer=False, nullable=True):
    try:
        result = pd.to_numeric(values, errors="raise")
        array = result.to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(array).any() or (not nullable and np.isnan(array).any()):
            raise ValueError
        if integer and not np.equal(array[~np.isnan(array)] % 1, 0).all():
            raise ValueError
        return result.astype("Int64" if integer else "Float64")
    except (ValueError, TypeError, OverflowError) as exc:
        raise NnInputContractError("invalid numeric input") from exc


def _category(value):
    if pd.isna(value):
        return pd.NA
    if isinstance(value, (bool, Integral)):
        return str(int(value))
    if isinstance(value, Real):
        if not np.isfinite(value):
            raise NnInputContractError("invalid categorical input")
        return str(int(value)) if value == int(value) else str(value)
    if not isinstance(value, str):
        raise NnInputContractError("invalid categorical input")
    return value


def _normalize(frame, columns, fields):
    columns = list(dict.fromkeys(columns))
    if frame.columns.has_duplicates or set(frame.columns) != set(columns):
        raise NnInputContractError("input columns differ from the requested contract")
    out = frame.loc[:, columns].copy(deep=True).reset_index(drop=True)
    for name in ENTRY_KEY:
        out[name] = _ids(out[name])
        if out[name].isna().any():
            raise NnInputContractError("missing entry key")
    if out.duplicated(list(ENTRY_KEY)).any():
        raise NnInputContractError("duplicate entry key")
    out["held_date"] = _dates(out.held_date)
    for field in fields:
        if field.name in out:
            out[field.name] = (_numbers(out[field.name]) if field.kind == "numeric"
                               else out[field.name].map(_category).astype("string"))
    for name in STATS_METADATA[:2]:
        out[name] = _dates(out[name], nullable=True)
        if out[name].gt(out.held_date).any():
            raise NnInputContractError("statistics cutoff is after the event date")
    for name in STATS_FLAGS:
        values = _numbers(out[name], integer=True, nullable=False)
        if not values.isin([0, 1]).all():
            raise NnInputContractError("invalid statistics missing flag")
        out[name] = values.astype("boolean")
    for cutoff, (entities, prefixes) in _STATS_CUTOFF_GROUPS.items():
        unknown = out[cutoff].isna()
        if not unknown.any():
            continue
        # A missing lookup has no reference date. Preserve it as unknown rather
        # than inventing a date; only absent statistics/zero sample counts qualify.
        if not out.loc[unknown, [f"{entity}_stats_missing" for entity in entities]].all().all():
            raise NnInputContractError("statistics values require a known cutoff")
        for field in fields:
            if field.name in out and field.name.startswith(prefixes):
                values = out.loc[unknown, field.name]
                absent = values.isna()
                if "_starts" in field.name:
                    absent = absent | values.eq(0).fillna(False)
                if not absent.all():
                    raise NnInputContractError("statistics values require a known cutoff")
    return out


class NnRaceInputs:
    """Validated current entries and reusable horse histories with defensive copies.

    This is an event-date contract, not historical publication-time reconstruction.
    No current-race targets or odds are exposed here.
    """

    def __init__(self, entries: pd.DataFrame, history: pd.DataFrame, *,
                 query: NnInputQuery, contract: NnFeatureContract,
                 source_revision: str, captured_at: datetime):
        query.validate_contract(contract)
        if not source_revision or captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise NnInputContractError("source revision and timezone-aware capture time are required")
        current = _normalize(entries, (*ENTRY_METADATA, *query.feature_names, *STATS_METADATA), contract.pre_race)
        past = _normalize(history, (*HISTORY_METADATA, *query.feature_names,
                                  *query.history_result_names, *STATS_METADATA),
                          (*contract.pre_race, *contract.history_results))
        for name in ("horse_number", "history_end_no", "active_entrant_count"):
            current[name] = _numbers(current[name], integer=True, nullable=False)
        if current.horse_number.le(0).any() or current.history_end_no.lt(0).any():
            raise NnInputContractError("invalid horse number or history endpoint")
        if current.duplicated(["race_id", "horse_number"]).any():
            raise NnInputContractError("duplicate horse number in a race")
        if not current.held_date.between(pd.Timestamp(query.from_date), pd.Timestamp(query.to_date)).all():
            raise NnInputContractError("entries outside requested dates")
        if query.max_races is not None and current.race_id.nunique() > query.max_races:
            raise NnInputContractError("too many target races")
        if not current.groupby("race_id").held_date.nunique().eq(1).all():
            raise NnInputContractError("inconsistent race date")
        if not current.groupby("race_id").kettonum.transform("size").eq(current.active_entrant_count).all():
            raise NnInputContractError("incomplete race field")
        current["last_history_race_id"] = _ids(current.last_history_race_id)
        current["last_history_held_date"] = _dates(current.last_history_held_date, nullable=True)
        current["days_since_last_run"] = _numbers(current.days_since_last_run, integer=True)
        past["run_no"] = _numbers(past.run_no, integer=True, nullable=False)
        past = past.sort_values(["kettonum", "run_no"]).reset_index(drop=True)
        if not past.run_no.eq(past.groupby("kettonum").cumcount() + 1).all():
            raise NnInputContractError("history must contain complete consecutive prefixes")
        if past.groupby("kettonum").held_date.diff().dropna().lt(pd.Timedelta(0)).any():
            raise NnInputContractError("history is not chronological")
        bounds = current.groupby("kettonum").history_end_no.max()
        actual = past.groupby("kettonum").run_no.max().reindex(bounds.index, fill_value=0)
        if not actual.eq(bounds).all() or not set(past.kettonum) <= set(bounds.index):
            raise NnInputContractError("history prefix does not match requested endpoints")
        endpoints = past[["kettonum", "run_no", "race_id", "held_date"]].rename(
            columns={"run_no": "history_end_no", "race_id": "endpoint_id", "held_date": "endpoint_date"})
        checked = current.merge(endpoints, on=["kettonum", "history_end_no"], how="left", validate="many_to_one")
        has_history = checked.history_end_no.gt(0)
        if (checked.loc[has_history, "endpoint_date"].isna().any()
                or checked.loc[has_history, "endpoint_date"].ge(checked.loc[has_history, "held_date"]).any()
                or not checked.last_history_race_id.fillna("").eq(checked.endpoint_id.fillna("")).all()
                or not checked.last_history_held_date.fillna(pd.Timestamp.min).eq(
                    checked.endpoint_date.fillna(pd.Timestamp.min)).all()
                or not checked.days_since_last_run.fillna(-1).eq(
                    (checked.held_date - checked.endpoint_date).dt.days.fillna(-1)).all()):
            raise NnInputContractError("history endpoint identity or date mismatch")
        following = endpoints.rename(columns={"endpoint_date": "next_date"}).drop(columns="endpoint_id")
        following["history_end_no"] -= 1
        checked = checked.merge(following, on=["kettonum", "history_end_no"], how="left", validate="many_to_one")
        if checked.next_date.lt(checked.held_date).any():
            raise NnInputContractError("history endpoint omits an eligible past run")
        self._entries = current.sort_values(["held_date", "race_id", "horse_number"]).reset_index(drop=True)
        self._history = past
        self._query, self._contract = query, contract
        self._source_revision = str(source_revision)
        self._captured_at = captured_at.astimezone(UTC)

    @property
    def entries(self) -> pd.DataFrame:
        return self._entries.copy(deep=True)

    @property
    def history(self) -> pd.DataFrame:
        return self._history.copy(deep=True)

    @property
    def query(self) -> NnInputQuery:
        return self._query

    @property
    def contract(self) -> NnFeatureContract:
        return self._contract

    @property
    def source_revision(self) -> str:
        return self._source_revision

    @property
    def captured_at(self) -> datetime:
        return self._captured_at


class NnTrainingInputs:
    """Targets are aligned by identity; missing targets remain unknown, not losses."""

    def __init__(self, inputs: NnRaceInputs, targets: pd.DataFrame):
        if targets.columns.has_duplicates or set(targets) != set((*ENTRY_KEY, *TARGET_COLUMNS)):
            raise NnInputContractError("invalid target columns")
        out = targets.copy(deep=True)
        for name in ENTRY_KEY:
            out[name] = _ids(out[name])
        if out[list(ENTRY_KEY)].isna().any().any() or out.duplicated(list(ENTRY_KEY)).any():
            raise NnInputContractError("missing or duplicate target key")
        expected = inputs.entries.loc[:, list(ENTRY_KEY)]
        check = expected.merge(out, on=list(ENTRY_KEY), how="outer", indicator=True, validate="one_to_one")
        if not check._merge.eq("both").all():
            raise NnInputContractError("target keys differ from the full entrant set")
        for name in TARGET_COLUMNS:
            out[name] = _numbers(out[name], integer=True)
        if out.result_order.dropna().le(0).any():
            raise NnInputContractError("invalid finishing position")
        for name in ("is_win", "is_place"):
            if not out[name].dropna().isin([0, 1]).all():
                raise NnInputContractError("invalid binary target")
            out[name] = out[name].astype("boolean")
        self._inputs = inputs
        self._targets = expected.merge(out, on=list(ENTRY_KEY), validate="one_to_one")

    @property
    def inputs(self) -> NnRaceInputs:
        return self._inputs

    @property
    def targets(self) -> pd.DataFrame:
        return self._targets.copy(deep=True)
