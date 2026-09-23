"""Read an NN field and its reusable run prefixes under one DB read snapshot."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
import re

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from harp.core.nn.contracts import (
    ENTRY_METADATA, HISTORY_METADATA, STATS_METADATA, TARGET_COLUMNS,
    NnFeatureContract, NnInputContractError, NnInputQuery, NnRaceInputs, NnTrainingInputs,
)


def _quote(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)?", name):
        raise NnInputContractError("invalid physical NN input identifier")
    return ".".join(f'"{part}"' for part in name.split("."))


@dataclass(frozen=True)
class NnInputMapping:
    entries_table: str = "mart.m_nn_race_entry"
    history_table: str = "intermediate.int_race_entry_run_record"
    targets_table: str = "intermediate.int_race_entry_outcome"
    entry_columns: dict[str, str] = field(default_factory=dict)
    history_columns: dict[str, str] = field(default_factory=dict)
    target_columns: dict[str, str] = field(default_factory=dict)


class SqlNnInputRepository:
    """Full fields, no odds joins, and nullable training targets.

    Call after the dbt NN build completes. A repeatable-read snapshot prevents
    reads drifting during extraction; endpoint checks also detect stale numbering.
    Neither this adapter nor a capture timestamp reconstructs historical live data.
    """

    def __init__(self, *, engine: Engine, mapping: NnInputMapping, contract: NnFeatureContract):
        self._engine, self._contract = engine, contract
        self._mapping = NnInputMapping(**json.loads(json.dumps(asdict(mapping))))

    def load_training_inputs(self, query: NnInputQuery) -> NnTrainingInputs:
        inputs, targets = self._load(query, training=True)
        return NnTrainingInputs(inputs, targets)

    def load_prediction_inputs(self, query: NnInputQuery) -> NnRaceInputs:
        inputs, _ = self._load(query, training=False)
        return inputs

    def _load(self, query: NnInputQuery, *, training: bool):
        query.validate_contract(self._contract)
        mapping = self._mapping
        entry_columns = list(dict.fromkeys((*ENTRY_METADATA, *query.feature_names, *STATS_METADATA)))
        history_columns = list(dict.fromkeys((*HISTORY_METADATA, *query.feature_names,
                                             *query.history_result_names, *STATS_METADATA)))

        def col(alias, columns, name):
            physical = columns.get(name, name)
            if not isinstance(physical, str) or "." in physical:
                raise NnInputContractError("column mappings must be unqualified")
            return f"{alias}.{_quote(physical)}"

        def h(name):
            return col("h", mapping.history_columns, name)

        selected = ", ".join(f'{col("src", mapping.entry_columns, name)} AS {_quote(name)}' for name in entry_columns)
        date_col = col("src", mapping.entry_columns, "held_date")
        race_col = col("src", mapping.entry_columns, "race_id")
        cte = f'''WITH candidates AS (
            SELECT {selected}, DENSE_RANK() OVER (ORDER BY {date_col}, {race_col}) AS selected_race_no
            FROM {_quote(mapping.entries_table)} src
            WHERE {date_col} >= :from_date AND {date_col} <= :to_date
        ), selected_entries AS (
            SELECT * FROM candidates {"WHERE selected_race_no <= :max_races" if query.max_races else ""}
        )'''
        entry_sql = cte + f''' SELECT {", ".join("e." + _quote(name) for name in entry_columns)},
            COALESCE((SELECT MAX({h("run_no")}) FROM {_quote(mapping.history_table)} h
                      WHERE {h("kettonum")} = e.kettonum AND {h("held_date")} < e.held_date), 0)
                AS source_history_end_no
            FROM selected_entries e'''
        history_sql = cte + f''', bounds AS (
            SELECT kettonum, MAX(history_end_no) AS end_no FROM selected_entries GROUP BY kettonum
        ) SELECT {", ".join(h(name) + " AS " + _quote(name) for name in history_columns)}
          FROM {_quote(mapping.history_table)} h JOIN bounds b
            ON {h("kettonum")} = b.kettonum AND {h("run_no")} <= b.end_no
          WHERE b.end_no > 0'''
        params = {"from_date": query.from_date, "to_date": query.to_date, "max_races": query.max_races}
        targets = None
        try:
            with self._engine.connect() as connection:
                if connection.dialect.name == "postgresql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    if connection.dialect.name == "postgresql":
                        connection.execute(text("SET TRANSACTION READ ONLY"))
                    # SQLite's legacy driver does not begin transactions for SELECT.
                    elif connection.dialect.name == "sqlite":
                        connection.exec_driver_sql("BEGIN")
                    def read(sql):
                        return pd.read_sql_query(text(sql), connection, params=params,
                                                 coerce_float=False, dtype_backend="numpy_nullable")
                    entries = read(entry_sql)
                    expected_end = entries.pop("source_history_end_no")
                    try:
                        matches = pd.to_numeric(entries.history_end_no, errors="raise").eq(
                            pd.to_numeric(expected_end, errors="raise"))
                    except (ValueError, TypeError) as exc:
                        raise NnInputContractError("invalid source history endpoint") from exc
                    if not matches.fillna(False).all():
                        raise NnInputContractError("stale history endpoint; rebuild NN current entries after history")
                    history = read(history_sql)
                    if training:
                        targets = read(cte + f''' SELECT e.race_id, e.kettonum,
                            {", ".join(col("t", mapping.target_columns, name) + " AS " + _quote(name) for name in TARGET_COLUMNS)}
                            FROM selected_entries e LEFT JOIN {_quote(mapping.targets_table)} t
                            ON e.race_id = {col("t", mapping.target_columns, "race_id")}
                           AND e.kettonum = {col("t", mapping.target_columns, "kettonum")}''')
        except SQLAlchemyError as exc:
            original = getattr(exc, "orig", None)
            code = getattr(original, "sqlstate", None) or getattr(original, "pgcode", "")
            if str(code).startswith("42") or "no such" in str(exc).lower():
                raise NnInputContractError("source schema does not satisfy the NN input mapping") from None
            raise RuntimeError("NN input source could not be read") from None
        revision = sha256(json.dumps(asdict(mapping), sort_keys=True).encode()).hexdigest()
        # The legacy outcome mart can mark result_order=0 as placed via <= 3.
        # Zero is an unavailable finishing position, not a real placing. Keep
        # the entrant and let Dataset admission handle the unknown teacher.
        if targets is not None:
            unknown = pd.to_numeric(targets.result_order, errors="coerce").eq(0)
            targets.loc[unknown, list(TARGET_COLUMNS)] = pd.NA
        if "result_order" in history:
            unknown = pd.to_numeric(history.result_order, errors="coerce").eq(0)
            history.loc[unknown, "result_order"] = pd.NA
        return NnRaceInputs(entries, history, query=query, contract=self._contract,
                            source_revision=revision, captured_at=datetime.now(UTC)), targets
