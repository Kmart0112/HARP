"""Immutable final-odds teachers, independently replayable from the database."""
import errno
import json
import tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.odds_targets import (
    QUOTE_COLUMNS,
    REFERENCE_COLUMNS,
    FinalPlaceOddsBatch,
    NnOddsSnapshot,
    validate_snapshot_identity,
)


def _hash(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ParquetNnOddsSnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, snapshot: NnOddsSnapshot) -> str:
        frame, coverage = snapshot.frame, snapshot.coverage
        manifest = {"version": 1, "kind": "nn_final_place_odds", "usage": "auxiliary_target",
                    "prepared_dataset_id": snapshot.prepared_dataset_id,
                    "input_dataset_id": snapshot.input_dataset_id,
                    "entry_keys_sha256": snapshot.entry_keys_sha256,
                    "captured_at": snapshot.captured_at.isoformat(), "source": snapshot.source,
                    "statuses": {str(k): int(v) for k, v in frame.status.value_counts().items()}, "files": {}}
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=self.root) as temporary:
            directory = Path(temporary)
            frame.to_parquet(directory / "odds.parquet", index=False)
            coverage.to_csv(directory / "coverage.csv", index=False)
            for name, rows in (("odds.parquet", len(frame)), ("coverage.csv", len(coverage))):
                manifest["files"][name] = {"sha256": _hash(directory / name), "rows": rows}
            encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
            identity = sha256(encoded).hexdigest()
            (directory / "manifest.json").write_bytes(encoded)
            self._read(directory, identity)
            try:
                directory.rename(self.root / identity)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                self.load(identity)
        return identity

    def load(self, snapshot_id: str) -> NnOddsSnapshot:
        validate_snapshot_identity(snapshot_id)
        return self._read(self.root / snapshot_id, snapshot_id)

    def _read(self, directory, identity):
        try:
            encoded = (directory / "manifest.json").read_bytes()
            if sha256(encoded).hexdigest() != identity:
                raise NnInputContractError("final odds manifest integrity failure")
            manifest = json.loads(encoded)
            if (manifest["version"] != 1 or manifest["kind"] != "nn_final_place_odds"
                    or manifest["usage"] != "auxiliary_target"):
                raise NnInputContractError("unsupported final odds snapshot kind or version")
            if set(manifest["files"]) != {"odds.parquet", "coverage.csv"}:
                raise NnInputContractError("invalid final odds snapshot files")
            for name, meta in manifest["files"].items():
                if _hash(directory / name) != meta["sha256"]:
                    raise NnInputContractError("final odds file integrity failure")
            frame = pd.read_parquet(directory / "odds.parquet")
            coverage = pd.read_csv(directory / "coverage.csv")
            expected_columns = set(REFERENCE_COLUMNS + QUOTE_COLUMNS + ["status"])
            if frame.columns.has_duplicates or set(frame.columns) != expected_columns:
                raise NnInputContractError("final odds snapshot columns differ from contract")
            if len(frame) != manifest["files"]["odds.parquet"]["rows"] or len(coverage) != manifest["files"]["coverage.csv"]["rows"]:
                raise NnInputContractError("final odds row count integrity failure")
            batch = FinalPlaceOddsBatch(frame[QUOTE_COLUMNS],
                                       captured_at=datetime.fromisoformat(manifest["captured_at"]), source=manifest["source"])
            snapshot = NnOddsSnapshot(frame[REFERENCE_COLUMNS], batch,
                                      prepared_dataset_id=manifest["prepared_dataset_id"],
                                      input_dataset_id=manifest["input_dataset_id"])
            if snapshot.entry_keys_sha256 != manifest["entry_keys_sha256"]:
                raise NnInputContractError("final odds reference identity mismatch")
            if not snapshot.frame.status.equals(frame.status):
                raise NnInputContractError("final odds status contradicts source values")
            if snapshot.frame.status.value_counts().to_dict() != manifest["statuses"]:
                raise NnInputContractError("final odds status counts mismatch")
            pd.testing.assert_frame_equal(snapshot.coverage, coverage, check_dtype=False, atol=1e-12, rtol=1e-12)
            return snapshot
        except NnInputContractError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, AssertionError) as exc:
            raise NnInputContractError("final odds snapshot is missing or invalid") from exc
