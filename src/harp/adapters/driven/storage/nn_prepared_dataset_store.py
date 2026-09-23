"""Content-addressed preparation recipes referencing immutable Parquet inputs."""
from dataclasses import asdict
import errno
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import HISTORY_RELATIVE_NAMES
from harp.core.nn.preprocessing import NnCategoryState, NnNumericState, NnPreprocessingState, NnTablePreprocessor
from harp.core.nn.split import NnDatasetConfig, NnRacePartition
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe


def _check_identity(identity: str) -> None:
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise NnInputContractError("invalid NN Dataset identity")


def _decode_table(document: dict) -> NnTablePreprocessor:
    return NnTablePreprocessor(
        tuple(NnNumericState(**state) for state in document["numeric"]),
        tuple(NnCategoryState(**state) for state in document["categorical"]),
    )


class JsonNnPreparedDatasetStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, recipe: NnPreparedDatasetRecipe) -> str:
        _check_identity(recipe.input_dataset_id)
        document = {
            "version": 1, "kind": "nn_prepared_dataset", "target": "is_place",
            "history_padding": "right", "history_order": "oldest_first",
            "history_relative_names": HISTORY_RELATIVE_NAMES,
            "recipe": asdict(recipe),
        }
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
        identity = sha256(encoded).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=self.root) as temporary:
            directory = Path(temporary)
            (directory / "manifest.json").write_bytes(encoded)
            self._read(directory, identity)
            try:
                directory.rename(self.root / identity)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                self.load(identity)
        return identity

    def load(self, prepared_dataset_id: str) -> NnPreparedDatasetRecipe:
        _check_identity(prepared_dataset_id)
        return self._read(self.root / prepared_dataset_id, prepared_dataset_id)

    def _read(self, directory: Path, identity: str) -> NnPreparedDatasetRecipe:
        try:
            encoded = (directory / "manifest.json").read_bytes()
            if sha256(encoded).hexdigest() != identity:
                raise NnInputContractError("NN preparation manifest integrity failure")
            document = json.loads(encoded)
            if (document["version"] != 1 or document["kind"] != "nn_prepared_dataset"
                    or document["target"] != "is_place" or document["history_padding"] != "right"
                    or document["history_order"] != "oldest_first"
                    or tuple(document["history_relative_names"]) != HISTORY_RELATIVE_NAMES):
                raise NnInputContractError("unsupported NN preparation version or layout")
            recipe = document["recipe"]
            _check_identity(recipe["input_dataset_id"])
            return NnPreparedDatasetRecipe(
                recipe["input_dataset_id"], NnDatasetConfig(**recipe["config"]),
                NnPreprocessingState(**{name: _decode_table(recipe["preprocessing"][name]) for name in ("current", "history")}),
                tuple(NnRacePartition(**part) for part in recipe["partitions"]),
            )
        except NnInputContractError:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise NnInputContractError("NN preparation manifest is missing or invalid") from exc
