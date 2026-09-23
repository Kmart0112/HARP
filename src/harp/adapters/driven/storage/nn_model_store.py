"""Immutable epoch snapshots plus an atomic latest pointer for each training run."""
from dataclasses import asdict
import errno
from hashlib import sha256
import json
from pathlib import Path
import pickle
import re
import tempfile
from uuid import uuid4

import torch

from harp.core.nn.config import resolve_nn_training_recipe
from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.tensor_batch import NnInputSpec
from harp.interface.ports.nn_training_ports import StoredNnCheckpoint
from .nn_prepared_dataset_store import decode_nn_preprocessing_state


def _encoded(document):
    return json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(value, length):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{" + str(length) + r"}", value):
        raise NnInputContractError("invalid NN model artifact identity")


def _atomic_json(path: Path, document):
    temporary = path.with_name(f".pending-{uuid4().hex}.json")
    try:
        temporary.write_bytes(_encoded(document))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class TorchNnModelStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def create_run(self, metadata: dict) -> str:
        encoded = _encoded(metadata)
        identity = uuid4().hex
        directory = self.root / identity
        directory.mkdir(parents=True, exist_ok=False)
        _atomic_json(directory / "run.json", {"metadata": metadata, "sha256": sha256(encoded).hexdigest()})
        return identity

    def save_checkpoint(self, run_id: str, checkpoint: dict) -> str:
        _identity(run_id, 32)
        run = self.root / run_id
        document = json.loads((run / "run.json").read_bytes())
        if sha256(_encoded(document["metadata"])).hexdigest() != document["sha256"]:
            raise NnInputContractError("NN run metadata integrity failure")
        checkpoints = run / "checkpoints"
        checkpoints.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=checkpoints) as temporary:
            directory = Path(temporary)
            torch.save(checkpoint["best_weights"], directory / "best_weights.pt")
            torch.save({key: value for key, value in checkpoint.items() if key != "best_weights"}, directory / "last_checkpoint.pt")
            (directory / "metadata.json").write_bytes(_encoded(document["metadata"]))
            (directory / "metrics.json").write_bytes(_encoded(checkpoint["metrics_history"]))
            names = ("best_weights.pt", "last_checkpoint.pt", "metadata.json", "metrics.json")
            manifest = {"version": 1, "kind": "nn_transformer_checkpoint", "run_id": run_id,
                        "epoch": checkpoint["epoch"], "files": {name: _digest(directory / name) for name in names}}
            encoded = _encoded(manifest)
            identity = sha256(encoded).hexdigest()
            (directory / "manifest.json").write_bytes(encoded)
            self._read(directory, run_id, identity)
            try:
                directory.rename(checkpoints / identity)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                self.load_checkpoint(run_id, identity)
        _atomic_json(run / "latest.json", {"checkpoint_id": identity, "epoch": checkpoint["epoch"]})
        return identity

    def load_checkpoint(self, run_id: str, checkpoint_id: str | None = None) -> StoredNnCheckpoint:
        _identity(run_id, 32)
        if checkpoint_id is None:
            try:
                checkpoint_id = json.loads((self.root / run_id / "latest.json").read_bytes())["checkpoint_id"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise NnInputContractError("NN run has no valid published checkpoint") from exc
        _identity(checkpoint_id, 64)
        return self._read(self.root / run_id / "checkpoints" / checkpoint_id, run_id, checkpoint_id)

    def _read(self, directory: Path, run_id: str, checkpoint_id: str) -> StoredNnCheckpoint:
        try:
            encoded = (directory / "manifest.json").read_bytes()
            if sha256(encoded).hexdigest() != checkpoint_id:
                raise NnInputContractError("NN checkpoint manifest integrity failure")
            manifest = json.loads(encoded)
            if (manifest["version"] != 1 or manifest["kind"] != "nn_transformer_checkpoint" or manifest["run_id"] != run_id):
                raise NnInputContractError("unsupported NN checkpoint identity/version")
            names = {"best_weights.pt", "last_checkpoint.pt", "metadata.json", "metrics.json"}
            if set(manifest["files"]) != names:
                raise NnInputContractError("invalid NN checkpoint files")
            for name in names:
                if _digest(directory / name) != manifest["files"][name]:
                    raise NnInputContractError("NN checkpoint file integrity failure")
            metadata = json.loads((directory / "metadata.json").read_bytes())
            recipe = resolve_nn_training_recipe(metadata["recipe"])
            preprocessing = decode_nn_preprocessing_state(metadata["preprocessing"])
            if _encoded(asdict(NnInputSpec.from_preprocessing(preprocessing))) != _encoded(metadata["input_spec"]):
                raise NnInputContractError("saved NN input specification differs from preprocessing")
            checkpoint = torch.load(directory / "last_checkpoint.pt", map_location="cpu", weights_only=True)
            checkpoint["best_weights"] = torch.load(directory / "best_weights.pt", map_location="cpu", weights_only=True)
            if (checkpoint["version"] != 1 or checkpoint["epoch"] != manifest["epoch"]
                    or checkpoint["metrics_history"] != json.loads((directory / "metrics.json").read_bytes())):
                raise NnInputContractError("inconsistent NN checkpoint state")
            return StoredNnCheckpoint(run_id, checkpoint_id, metadata, checkpoint,
                                      str(directory.resolve()), recipe, preprocessing)
        except NnInputContractError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, EOFError, pickle.UnpicklingError) as exc:
            raise NnInputContractError("NN checkpoint is missing or invalid") from exc
