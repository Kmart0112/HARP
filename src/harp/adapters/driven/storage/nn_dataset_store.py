"""Atomic, content-addressed persistence for longitudinal NN inputs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import errno
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile

import pandas as pd

from harp.core.nn.contracts import NnInputContractError, NnInputQuery, NnRaceInputs, NnTrainingInputs
from harp.interface.ports.nn_storage_ports import StoredNnDataset, StoredNnPredictionInputs
from .nn_feature_contract import decode_nn_feature_contract


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class _NnInputStore:
    def __init__(self, root: str | Path, *, kind: str):
        self.root, self.kind = Path(root), kind

    def save(self, inputs, metadata: dict) -> str:
        if not isinstance(metadata, dict):
            raise NnInputContractError("snapshot metadata must be a dictionary")
        training = self.kind == "training"
        if (training and not isinstance(inputs, NnTrainingInputs)) or (not training and not isinstance(inputs, NnRaceInputs)):
            raise NnInputContractError("wrong NN input kind for this store")
        base = inputs.inputs if training else inputs
        frames = {"entries.parquet": base.entries, "history.parquet": base.history}
        if training:
            frames["targets.parquet"] = inputs.targets
        manifest = {
            "version": 1, "kind": self.kind, "availability_basis": "event_date",
            "query": asdict(base.query), "feature_contract": asdict(base.contract),
            "source_revision": base.source_revision, "captured_at": base.captured_at.isoformat(),
            "metadata": metadata, "files": {},
        }
        # Reject unserializable metadata before writing even a temporary artifact.
        json.dumps(manifest, allow_nan=False)
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=self.root) as temporary:
            directory = Path(temporary)
            for name, frame in frames.items():
                frame.to_parquet(directory / name, index=False)
                manifest["files"][name] = {"sha256": _hash_file(directory / name), "rows": len(frame)}
            encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
            identity = sha256(encoded).hexdigest()
            (directory / "manifest.json").write_bytes(encoded)
            # Validate the serialized representation before publishing it.
            self._read(directory, identity)
            destination = self.root / identity
            if destination.exists():
                self.load(identity)
            else:
                try:
                    directory.rename(destination)
                except OSError as exc:
                    if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                        raise
                    self.load(identity)
        return identity

    def load(self, identity: str):
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise NnInputContractError("invalid NN snapshot identity")
        return self._read(self.root / identity, identity)

    def _read(self, directory: Path, identity: str):
        try:
            encoded = (directory / "manifest.json").read_bytes()
            if sha256(encoded).hexdigest() != identity:
                raise NnInputContractError("NN manifest integrity failure")
            manifest = json.loads(encoded)
            if manifest["version"] != 1 or manifest["kind"] != self.kind or manifest["availability_basis"] != "event_date":
                raise NnInputContractError("unsupported NN snapshot version or kind")
            expected_files = {"entries.parquet", "history.parquet"}
            if self.kind == "training":
                expected_files.add("targets.parquet")
            if set(manifest["files"]) != expected_files or not isinstance(manifest["metadata"], dict):
                raise NnInputContractError("invalid NN snapshot contents")
            # Check ALL files before parsing any input values.
            for name in expected_files:
                if _hash_file(directory / name) != manifest["files"][name]["sha256"]:
                    raise NnInputContractError("NN input file integrity failure")
            frames = {name: pd.read_parquet(directory / name) for name in expected_files}
            if any(len(frame) != manifest["files"][name]["rows"] for name, frame in frames.items()):
                raise NnInputContractError("NN input row count integrity failure")
            inputs = NnRaceInputs(
                frames["entries.parquet"], frames["history.parquet"],
                query=NnInputQuery(**manifest["query"]),
                contract=decode_nn_feature_contract(manifest["feature_contract"]),
                source_revision=manifest["source_revision"],
                captured_at=datetime.fromisoformat(manifest["captured_at"]),
            )
            if self.kind == "training":
                return StoredNnDataset(NnTrainingInputs(inputs, frames["targets.parquet"]), manifest["metadata"])
            return StoredNnPredictionInputs(inputs, manifest["metadata"])
        except NnInputContractError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise NnInputContractError("NN snapshot is missing or invalid") from exc


class ParquetNnDatasetStore:
    def __init__(self, root: str | Path):
        self._store = _NnInputStore(root, kind="training")

    def save(self, inputs: NnTrainingInputs, metadata: dict) -> str:
        return self._store.save(inputs, metadata)

    def load(self, dataset_id: str) -> StoredNnDataset:
        return self._store.load(dataset_id)


class ParquetNnPredictionSnapshotStore:
    def __init__(self, root: str | Path):
        self._store = _NnInputStore(root, kind="prediction")

    def save(self, inputs: NnRaceInputs, metadata: dict) -> str:
        return self._store.save(inputs, metadata)

    def load(self, snapshot_id: str) -> StoredNnPredictionInputs:
        return self._store.load(snapshot_id)
