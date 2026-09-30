"""Read final auxiliary teachers under one read-only database snapshot."""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.odds_targets import (
    QUOTE_COLUMNS,
    FinalPlaceOddsBatch,
    FinalPlaceOddsQuery,
)


def _quote(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)?", name):
        raise NnInputContractError("invalid final odds SQL identifier")
    return ".".join(f'"{piece}"' for piece in name.split("."))


@dataclass(frozen=True)
class FinalOddsMapping:
    table: str = "core.fct_race_entry_final_odds"
    columns: dict[str, str] = field(default_factory=lambda: {
        "race_id": "race_id", "horse_number": "horse_number", "place_low": "odds_fukusho_low",
        "place_high": "odds_fukusho_high", "source_updated_at": "updated_at"})
    race_id_type: str = "bigint"
    staging_table: str | None = "staging.stg_n_odds_tanpuku"
    staging_columns: dict[str, str] = field(default_factory=lambda: {
        "race_id": "race_id", "horse_number": "horse_number", "place_low": "odds_fukusho_low",
        "place_high": "odds_fukusho_high"})
    source_timezone: str | None = None


class SqlFinalPlaceOddsRepository:
    def __init__(self, *, engine, mapping: FinalOddsMapping, batch_size: int = 5000):
        if type(batch_size) is not int or not 1 <= batch_size <= 5000:
            raise NnInputContractError("final odds batch size must be between 1 and 5000")
        self._engine = engine
        self._mapping = FinalOddsMapping(**json.loads(json.dumps(asdict(mapping))))
        self._batch_size = batch_size
        if mapping.race_id_type not in {"bigint", "text"}:
            raise NnInputContractError("unsupported final odds race ID binding")
        _quote(mapping.table)
        if mapping.staging_table:
            _quote(mapping.staging_table)
        for columns in (mapping.columns, mapping.staging_columns):
            for name in columns.values():
                if "." in name:
                    raise NnInputContractError("final odds column must be unqualified")
                _quote(name)

    def load(self, query: FinalPlaceOddsQuery) -> FinalPlaceOddsBatch:
        mapping = self._mapping
        keys = query.keys
        if mapping.race_id_type == "bigint":
            values = []
            for value in keys.race_id:
                if not value.isdecimal() or str(int(value)) != value or not 0 < int(value) < 2**63:
                    raise NnInputContractError("race ID does not satisfy integer source binding")
                values.append(int(value))
            keys["race_id"] = values

        def col(alias, name, *, staging=False):
            columns = mapping.staging_columns if staging else mapping.columns
            if name not in columns:
                raise NnInputContractError("missing final odds column mapping")
            return f"{alias}.{_quote(columns[name])}"

        chunks = []
        try:
            with self._engine.connect() as connection:
                if connection.dialect.name == "postgresql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    if connection.dialect.name == "postgresql":
                        connection.execute(text("SET TRANSACTION READ ONLY"))
                    elif connection.dialect.name == "sqlite":
                        connection.exec_driver_sql("BEGIN")
                    for offset in range(0, len(keys), self._batch_size):
                        part = keys.iloc[offset:offset + self._batch_size]
                        params, values = {}, []
                        for index, (race, horse) in enumerate(part.itertuples(index=False, name=None)):
                            params[f"r{index}"], params[f"h{index}"] = race, int(horse)
                            values.append(f"(:r{index}, :h{index})")
                        fields = ["k.race_id", "k.horse_number", f'{col("o", "race_id")} IS NOT NULL AS source_found']
                        fields += [f'{col("o", name)} AS {name}' for name in ("place_low", "place_high", "source_updated_at")]
                        joins = f'LEFT JOIN {_quote(mapping.table)} o ON {col("o", "race_id")}=k.race_id AND {col("o", "horse_number")}=k.horse_number'
                        if mapping.staging_table:
                            joins += f' LEFT JOIN {_quote(mapping.staging_table)} s ON {col("s", "race_id", staging=True)}=k.race_id AND {col("s", "horse_number", staging=True)}=k.horse_number'
                            fields += [f'{col("s", "race_id", staging=True)} IS NOT NULL AS staging_found']
                            fields += [f'{col("s", name, staging=True)} AS staging_{name}' for name in ("place_low", "place_high")]
                        sql = f'WITH requested(race_id,horse_number) AS (VALUES {",".join(values)}) SELECT {",".join(fields)} FROM requested k {joins}'
                        frame = pd.read_sql_query(text(sql), connection, params=params,
                                                  coerce_float=False, dtype_backend="numpy_nullable")
                        if len(frame) != len(part) or frame.duplicated(["race_id", "horse_number"]).any():
                            raise NnInputContractError("duplicate final odds source or staging key")
                        if mapping.staging_table:
                            matched = frame.source_found.eq(frame.staging_found)
                            for name in ("place_low", "place_high"):
                                left = pd.to_numeric(frame[name], errors="raise")
                                right = pd.to_numeric(frame[f"staging_{name}"], errors="raise")
                                matched &= left.eq(right).fillna(False) | (left.isna() & right.isna())
                            if not matched.all():
                                raise NnInputContractError("final odds differ from staging; rebuild source before capture")
                        frame["source_found"] = frame.source_found.astype(bool)
                        frame["race_id"] = frame.race_id.astype(str)
                        for name in ("place_low", "place_high"):
                            frame[name] = pd.to_numeric(frame[name], errors="raise").astype("float64")
                        times = pd.to_datetime(frame.source_updated_at, errors="raise")
                        if times.dt.tz is None:
                            if times.notna().any() and mapping.source_timezone is None:
                                raise NnInputContractError("source build timestamp requires timezone")
                            times = times.dt.tz_localize(mapping.source_timezone or "UTC")
                        frame["source_updated_at"] = times.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")
                        chunks.append(frame[QUOTE_COLUMNS])
        except SQLAlchemyError as exc:
            original = getattr(exc, "orig", None)
            code = getattr(original, "sqlstate", None) or getattr(original, "pgcode", "") or ""
            if code.startswith("42") or "no such" in str(exc).lower():
                raise NnInputContractError("final odds source schema does not satisfy mapping") from None
            raise RuntimeError("final odds source could not be read") from None
        frame = pd.concat(chunks, ignore_index=True)
        source = {"kind": "final", "mapping": asdict(mapping),
                  "revision": sha256(json.dumps(asdict(mapping), sort_keys=True).encode()).hexdigest(),
                  "staging_checked": mapping.staging_table is not None}
        return FinalPlaceOddsBatch(frame, captured_at=datetime.now(UTC), source=source)
