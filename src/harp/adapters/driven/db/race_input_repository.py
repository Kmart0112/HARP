"""SQL implementation of the consumer-owned race input Ports.

Physical relations and aliases are adapter configuration. Both co-located and
split odds layouts satisfy exactly the same Port, using one SQL statement.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from harp.core.odds import (
    ENTRY_KEY,
    ODDS_FEATURE_NAMES,
    QUOTE_COLUMNS,
    OddsContractError,
    normalize_entry_keys,
    select_odds,
)
from harp.core.race_inputs import RaceInputQuery, RaceInputs


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)?", value):
        raise OddsContractError("invalid physical identifier in input mapping")
    return ".".join(f'"{part}"' for part in value.split("."))


@dataclass(frozen=True)
class RaceInputMapping:
    entries_table: str
    entry_columns: dict[str, str] = field(default_factory=dict)
    quotes_table: str | None = None
    quote_columns: dict[str, str | None] = field(default_factory=dict)
    metadata_fields: tuple[str, ...] = ("scheduled_start_at", "num_starters")
    naive_timestamp_timezone: str | None = None
    preselected_minutes_before_start: int | None = None

    def entry(self, logical: str) -> str:
        return f'e.{_identifier(self.entry_columns.get(logical, logical))}'

    def quote(self, logical: str) -> str:
        column = self.quote_columns.get(logical, logical)
        if column is None:
            if logical not in {"available_at", "win_popularity"}:
                raise OddsContractError(f"required quote binding cannot be null: {logical}")
            return "NULL"
        return f'{"q" if self.quotes_table else "e"}.{_identifier(column)}'


class SqlRaceInputRepository:
    def __init__(self, *, engine: Engine, mapping: RaceInputMapping):
        self._engine = engine
        self._mapping = mapping

    def load_prediction_input(self, query: RaceInputQuery) -> RaceInputs:
        if query.target_names:
            raise OddsContractError("prediction cannot request post-race targets")
        return self._load(query)

    def load_training_input(self, query: RaceInputQuery) -> RaceInputs:
        if query.odds_policy.mode != "pre_start":
            raise OddsContractError("training requires pre_start odds")
        return self._load(query)

    def _load(self, query: RaceInputQuery) -> RaceInputs:
        mapping = self._mapping
        if mapping.preselected_minutes_before_start is not None and (
            query.odds_policy.mode != "pre_start"
            or query.odds_policy.minutes_before_start != mapping.preselected_minutes_before_start
        ):
            raise OddsContractError("preselected odds source does not support the requested policy")
        entry_fields = list(dict.fromkeys([*ENTRY_KEY, "held_date", *mapping.metadata_fields,
                                           *(name for name in query.feature_names if name not in ODDS_FEATURE_NAMES),
                                           *query.target_names]))
        if "held_year" in entry_fields:
            entry_fields.remove("held_year")  # Deterministically derived from held_date.
        fields = [f'{mapping.entry(name)} AS {_identifier(name)}' for name in entry_fields]
        fields += [f'{mapping.quote(name)} AS {_identifier("quote_" + name)}'
                   for name in QUOTE_COLUMNS if name not in ENTRY_KEY]
        fields.append('e."entry_multiplicity"')
        where = [f'{mapping.entry("held_date")} >= :from_date', f'{mapping.entry("held_date")} <= :to_date']
        params = {"from_date": query.from_date, "to_date": query.to_date}
        operators = {"eq": "=", "ne": "<>", "neq": "<>", "gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}
        for index, (key, value) in enumerate(query.filters.items()):
            logical, _, operation = key.partition("__")
            operation = operation or "eq"
            column = mapping.entry(logical)
            if value is None and operation in {"eq", "ne", "neq"}:
                where.append(f"{column} IS {'NOT ' if operation != 'eq' else ''}NULL")
            elif operation == "in" and isinstance(value, (list, tuple)):
                names = []
                for number, item in enumerate(value):
                    parameter = f"filter_{index}_{number}"
                    params[parameter] = item
                    names.append(":" + parameter)
                where.append(f"{column} IN ({', '.join(names)})" if names else "1=0")
            elif operation in operators:
                parameter = f"filter_{index}"
                params[parameter] = value
                where.append(f"{column} {operators[operation]} :{parameter}")
            else:
                raise OddsContractError(f"unsupported logical filter: {key}")
        if "is_scratched" in mapping.metadata_fields:
            where.append(f'{mapping.entry("is_scratched")} = false')
        joins = ""
        if mapping.quotes_table:
            joins = f'LEFT JOIN {_identifier(mapping.quotes_table)} q ON ' + " AND ".join(
                f"{mapping.entry(key)} = {mapping.quote(key)}" for key in ENTRY_KEY)
        limit = ""
        if query.max_races is not None:
            params["max_races"] = query.max_races
            limit = 'WHERE e."race_rank" <= :max_races'
        # The rank is assigned before the odds join, so a limit never truncates a race.
        sql = f'''WITH selected_entries AS (
            SELECT e.*,
                COUNT(*) OVER (PARTITION BY {mapping.entry('race_id')}, {mapping.entry('horse_number')}) AS "entry_multiplicity",
                DENSE_RANK() OVER (ORDER BY {mapping.entry('held_date')} DESC, {mapping.entry('race_id')} DESC) AS "race_rank"
            FROM {_identifier(mapping.entries_table)} e
            WHERE {' AND '.join(where)}
        )
        SELECT {', '.join(fields)} FROM selected_entries e {joins} {limit}
        ORDER BY {mapping.entry('held_date')} DESC, {mapping.entry('race_id')} DESC, {mapping.entry('horse_number')} ASC'''
        try:
            with self._engine.connect() as connection:
                raw = pd.read_sql_query(text(sql), connection, params=params)
        except SQLAlchemyError as exc:
            # Do not expose connection URLs or driver messages containing credentials.
            original = getattr(exc, "orig", None)
            code = getattr(original, "sqlstate", None) or getattr(original, "pgcode", "")
            if str(code).startswith("42") or "no such" in str(exc).lower():
                raise OddsContractError("source schema does not satisfy the race input mapping") from None
            raise RuntimeError("race input source could not be read") from None
        if raw.entry_multiplicity.gt(1).any():
            raise OddsContractError("source schema: duplicate entry key")
        entries = normalize_entry_keys(raw[entry_fields].drop_duplicates(), name="source entries")
        dates = pd.to_datetime(entries.held_date, errors="raise")
        entries["held_date"] = dates.dt.strftime("%Y-%m-%d")
        entries["held_year"] = dates.dt.year.astype(int)
        numeric = set(query.feature_names).difference(query.categorical_features, ODDS_FEATURE_NAMES)
        for name in numeric.union(query.target_names):
            try:
                entries[name] = pd.to_numeric(entries[name], errors="raise")
            except (TypeError, ValueError):
                raise OddsContractError(f"{name}: invalid numeric input type") from None
            if np.isinf(entries[name].to_numpy(dtype=float, na_value=np.nan)).any():
                raise OddsContractError(f"{name}: non-finite numeric input")
        quotes = raw[[*ENTRY_KEY, *("quote_" + name for name in QUOTE_COLUMNS if name not in ENTRY_KEY)]].rename(
            columns={"quote_" + name: name for name in QUOTE_COLUMNS if name not in ENTRY_KEY})
        if mapping.naive_timestamp_timezone:
            def normalize_time(value):
                if pd.isna(value):
                    return pd.NaT
                stamp = pd.Timestamp(value)
                return stamp if stamp.tzinfo is not None else stamp.tz_localize(mapping.naive_timestamp_timezone)
            for name in ["published_at", "available_at"]:
                quotes[name] = quotes[name].map(normalize_time)
            if "scheduled_start_at" in entries:
                entries["scheduled_start_at"] = entries.scheduled_start_at.map(normalize_time)
        odds = select_odds(entries, quotes, query.odds_policy)
        revision = sha256(json.dumps({"entries": mapping.entries_table, "quotes": mapping.quotes_table,
                                     "entry_columns": mapping.entry_columns, "quote_columns": mapping.quote_columns,
                                     "timezone": mapping.naive_timestamp_timezone},
                                    sort_keys=True).encode()).hexdigest()
        return RaceInputs(entries, odds, source_revision=revision, captured_at=datetime.now(UTC))


def mart_input_mapping(table: str, *, quotes_table: str | None = None,
                       pre_start_minutes: int | None = None) -> RaceInputMapping:
    """Explicit dbt-to-application mapping; changing dbt never changes a Port."""
    return RaceInputMapping(
        entries_table=table, quotes_table=quotes_table,
        preselected_minutes_before_start=pre_start_minutes,
        quote_columns={"win_odds": "odds_tansho", "place_low": "odds_fukusho_low",
                       "place_high": "odds_fukusho_high", "win_popularity": "popularity",
                       "published_at": "odds_published_at", "available_at": "available_at"},
        metadata_fields=("scheduled_start_at", "num_starters", "active_entrant_count", "is_scratched", "horse_name",
                         "jyo_cd", "jyo_name", "round", "surface", "distance_m"),
    )
