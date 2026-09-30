"""Final odds are auxiliary teachers, separate from prediction-time features."""
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from numbers import Integral

import numpy as np
import pandas as pd

from harp.core.odds import normalize_entry_keys, utc_timestamp

from .contracts import NnInputContractError

KEYS = ["race_id", "horse_number"]
REFERENCE_COLUMNS = ["race_id", "kettonum", "horse_number", "held_date", "split"]
QUOTE_COLUMNS = [*KEYS, "place_low", "place_high", "source_found", "source_updated_at"]
STATUSES = ("available", "missing_row", "missing_value", "invalid_value")


@dataclass(frozen=True)
class NnOddsTransform:
    """Population moments of log midpoint, fitted on available training entrants."""
    mean: float
    scale: float
    training_entries: int

    def __post_init__(self):
        if (not np.isfinite(self.mean) or not np.isfinite(self.scale) or self.scale <= 0
                or type(self.training_entries) is not int or self.training_entries < 1):
            raise NnInputContractError("invalid NN odds transform")


def prepare_nn_odds_targets(snapshot, reference: pd.DataFrame, *, transform: NnOddsTransform | None = None):
    """Validate the sidecar identity and optionally fit train-only target moments."""
    if snapshot.entry_keys_sha256 != nn_odds_reference_hash(reference):
        raise NnInputContractError("odds snapshot differs from Dataset entries or splits")
    frame = snapshot.frame
    available = frame.status.eq("available")
    values = np.zeros(len(frame), dtype=np.float64)
    values[available] = np.log(frame.loc[available, "place_low"] / 2 + frame.loc[available, "place_high"] / 2)
    if transform is None:
        train = values[available & frame.split.eq("train")]
        transform = NnOddsTransform(float(train.mean()), float(train.std()) or 1.0, len(train))
    targets = frame[["race_id", "kettonum"]].copy()
    targets["odds_target"] = np.where(available, (values - transform.mean) / transform.scale, 0).astype(np.float32)
    targets["odds_mask"] = available.to_numpy()
    return targets, transform


def _columns(frame, expected):
    if frame.columns.has_duplicates or set(frame.columns) != set(expected):
        raise NnInputContractError("final odds columns differ from contract")


def _keys(frame):
    if not frame.race_id.map(lambda x: isinstance(x, (str, Integral)) and not isinstance(x, (bool, np.bool_))).all():
        raise NnInputContractError("unsafe final odds race ID")
    out = normalize_entry_keys(frame, name="final odds")
    if out.race_id.ne(out.race_id.str.strip()).any() or frame.race_id.map(lambda x: isinstance(x, (bool, np.bool_))).any():
        raise NnInputContractError("invalid final odds race ID")
    if frame.horse_number.map(lambda x: isinstance(x, (bool, np.bool_))).any():
        raise NnInputContractError("invalid final odds horse number")
    return out


def validate_snapshot_identity(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise NnInputContractError("invalid final odds snapshot or Dataset identity")


class FinalPlaceOddsQuery:
    def __init__(self, keys: pd.DataFrame):
        _columns(keys, KEYS)
        self._keys = _keys(keys).loc[:, KEYS]
        if self._keys.empty:
            raise NnInputContractError("final odds query requires entrants")

    @property
    def keys(self):
        return self._keys.copy(deep=True)


def select_nn_odds_reference(entries: pd.DataFrame, partitions) -> pd.DataFrame:
    """Reuse admitted races and their saved identities; never repartition/refit."""
    parts = pd.DataFrame(asdict(part) for part in partitions)
    if parts.empty or parts.race_id.duplicated().any():
        raise NnInputContractError("invalid saved NN partitions")
    if set(entries.race_id) != set(parts.race_id):
        raise NnInputContractError("saved partitions differ from input races")
    known = parts.loc[parts.exclusion_reason.isna()]
    out = entries[["race_id", "kettonum", "horse_number", "held_date"]].merge(
        known[["race_id", "held_date", "split", "entrant_count"]].rename(columns={"held_date": "partition_date"}),
        on="race_id", how="inner", validate="many_to_one")
    if not pd.to_datetime(out.held_date).eq(pd.to_datetime(out.partition_date)).all():
        raise NnInputContractError("saved partition date differs from entries")
    if not out.groupby("race_id").race_id.transform("size").eq(out.entrant_count).all():
        raise NnInputContractError("saved partition entrant count differs from entries")
    return normalize_nn_odds_reference(out[REFERENCE_COLUMNS])


def normalize_nn_odds_reference(frame: pd.DataFrame) -> pd.DataFrame:
    _columns(frame, REFERENCE_COLUMNS)
    out = _keys(frame)
    if out.empty or out.kettonum.isna().any():
        raise NnInputContractError("empty or missing NN odds reference")
    if not out.kettonum.map(lambda x: isinstance(x, (str, Integral)) and not isinstance(x, (bool, np.bool_))).all():
        raise NnInputContractError("unsafe NN horse identity")
    out["kettonum"] = out.kettonum.astype(str)
    if out.kettonum.str.strip().eq("").any() or out.kettonum.ne(out.kettonum.str.strip()).any():
        raise NnInputContractError("invalid NN horse identity")
    if out.duplicated(["race_id", "kettonum"]).any():
        raise NnInputContractError("duplicate NN horse identity")
    out["held_date"] = pd.to_datetime(out.held_date, errors="raise")
    if out.held_date.dt.tz is not None or out.held_date.isna().any() or not out.held_date.eq(out.held_date.dt.normalize()).all():
        raise NnInputContractError("invalid NN odds event date")
    if not out.split.isin(["train", "validation", "test"]).all():
        raise NnInputContractError("invalid NN odds split")
    if not out.groupby("race_id")[["held_date", "split"]].nunique().eq(1).all().all():
        raise NnInputContractError("inconsistent NN odds race partition")
    return out[REFERENCE_COLUMNS].sort_values(KEYS).reset_index(drop=True)


def nn_odds_reference_hash(reference: pd.DataFrame) -> str:
    out = normalize_nn_odds_reference(reference)
    out["held_date"] = out.held_date.dt.strftime("%Y-%m-%d")
    encoded = json.dumps(out.to_dict("records"), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256(encoded).hexdigest()


class FinalPlaceOddsBatch:
    def __init__(self, frame: pd.DataFrame, *, captured_at: datetime, source: dict):
        _columns(frame, QUOTE_COLUMNS)
        out = _keys(frame)
        if not out.source_found.map(lambda x: isinstance(x, (bool, np.bool_))).all():
            raise NnInputContractError("final odds source presence must be boolean")
        for name in ("place_low", "place_high"):
            if out[name].map(lambda x: isinstance(x, (bool, np.bool_))).any():
                raise NnInputContractError("invalid final odds numeric value")
            out[name] = pd.to_numeric(out[name], errors="raise").astype("float64")
        times = pd.to_datetime(out.source_updated_at, errors="raise")
        if times.notna().any() and times.dt.tz is None:
            raise NnInputContractError("source build timestamp requires timezone")
        out["source_updated_at"] = pd.to_datetime(times, utc=True).astype("datetime64[ns, UTC]")
        if out.loc[~out.source_found, ["place_low", "place_high", "source_updated_at"]].notna().any().any():
            raise NnInputContractError("absent final odds row contains source values")
        if not isinstance(source, dict) or source.get("kind") != "final" or not source.get("revision"):
            raise NnInputContractError("final odds require declared source provenance")
        self._source = json.loads(json.dumps(source, allow_nan=False))
        self._frame = out[QUOTE_COLUMNS].sort_values(KEYS).reset_index(drop=True)
        self.captured_at = utc_timestamp(captured_at, field="captured_at").to_pydatetime()

    @property
    def frame(self):
        return self._frame.copy(deep=True)

    @property
    def source(self):
        return json.loads(json.dumps(self._source))


class NnOddsSnapshot:
    def __init__(self, reference: pd.DataFrame, batch: FinalPlaceOddsBatch, *,
                 prepared_dataset_id: str, input_dataset_id: str):
        validate_snapshot_identity(prepared_dataset_id)
        validate_snapshot_identity(input_dataset_id)
        reference = normalize_nn_odds_reference(reference)
        aligned = reference.merge(batch.frame, on=KEYS, how="outer", indicator=True, validate="one_to_one")
        if not aligned._merge.eq("both").all():
            raise NnInputContractError("final odds keys differ from requested entrants")
        aligned = aligned.drop(columns="_merge")
        low, high = aligned.place_low, aligned.place_high
        valid = np.isfinite(low) & np.isfinite(high) & low.ge(1) & high.ge(low)
        aligned["status"] = np.select(
            [~aligned.source_found, low.isna() | high.isna(), ~valid],
            ["missing_row", "missing_value", "invalid_value"], default="available")
        if not (aligned.split.eq("train") & aligned.status.eq("available")).any():
            raise NnInputContractError("no available final odds in training split")
        self._frame = aligned.sort_values(KEYS).reset_index(drop=True)
        self.prepared_dataset_id, self.input_dataset_id = prepared_dataset_id, input_dataset_id
        self.entry_keys_sha256 = nn_odds_reference_hash(reference)
        self.captured_at, self._source = batch.captured_at, batch.source

    @property
    def frame(self):
        return self._frame.copy(deep=True)

    @property
    def source(self):
        return json.loads(json.dumps(self._source))

    @property
    def coverage(self):
        frame = self._frame.assign(year=self._frame.held_date.dt.year)
        totals = frame.groupby(["year", "split"]).size().rename("total_entries")
        counts = frame.groupby(["year", "split", "status"]).size().unstack(fill_value=0)
        counts = counts.reindex(columns=STATUSES, fill_value=0).stack(future_stack=True).rename("entries")
        result = counts.reset_index().merge(totals.reset_index(), on=["year", "split"])
        result["fraction"] = result.entries / result.total_entries
        return result
