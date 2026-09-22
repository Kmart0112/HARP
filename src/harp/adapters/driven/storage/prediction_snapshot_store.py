from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

import pandas as pd

from harp.core.odds import (
    ODDS_CONTRACT_VERSION,
    OddsBatch,
    OddsContractError,
    OddsPolicy,
)
from harp.core.race_inputs import RaceInputs
from harp.interface.ports.prediction_snapshot_ports import StoredPredictionInputs


class ParquetPredictionSnapshotStore:
    """Content-addressed input persistence with a manifest published by rename."""

    def __init__(self, root: str | Path):
        self._root = Path(root)

    def save(self, inputs: RaceInputs, metadata: dict) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=self._root) as temporary:
            directory = Path(temporary)
            inputs.frame.to_parquet(directory / "entries.parquet", index=False)
            inputs.odds.frame.to_parquet(directory / "odds.parquet", index=False)
            manifest = {
                "version": 1, "odds_contract_version": inputs.odds.contract_version,
                "policy": inputs.odds.policy.to_dict(), "availability_basis": inputs.odds.availability_basis,
                "source_revision": inputs.source_revision, "metadata": metadata,
                "captured_at": inputs.captured_at.isoformat() if inputs.captured_at else None,
                "files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                          for name in ["entries.parquet", "odds.parquet"]},
            }
            encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
            identity = hashlib.sha256(encoded).hexdigest()
            (directory / "manifest.json").write_bytes(encoded)
            destination = self._root / identity
            if destination.exists():
                self.load(identity)
            else:
                try:
                    directory.rename(destination)
                except FileExistsError:
                    self.load(identity)
        return identity

    def load(self, snapshot_id: str) -> StoredPredictionInputs:
        if not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
            raise OddsContractError("invalid prediction snapshot identity")
        directory = self._root / snapshot_id
        encoded = (directory / "manifest.json").read_bytes()
        if hashlib.sha256(encoded).hexdigest() != snapshot_id:
            raise OddsContractError("prediction snapshot manifest integrity failure")
        manifest = json.loads(encoded)
        if manifest["version"] != 1 or manifest["odds_contract_version"] != ODDS_CONTRACT_VERSION:
            raise OddsContractError("unsupported prediction snapshot contract")
        for name in ["entries.parquet", "odds.parquet"]:
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest["files"][name]:
                raise OddsContractError(f"prediction snapshot integrity failure: {name}")
        odds = OddsBatch(pd.read_parquet(directory / "odds.parquet"),
                         policy=OddsPolicy(**manifest["policy"]),
                         availability_basis=manifest["availability_basis"])
        inputs = RaceInputs(pd.read_parquet(directory / "entries.parquet"), odds, manifest["source_revision"], manifest.get("captured_at"))
        return StoredPredictionInputs(inputs, manifest["metadata"])
