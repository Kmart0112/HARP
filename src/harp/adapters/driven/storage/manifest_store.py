from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from harp.interface.ports import FileGatewayPort
from harp.shared.paths import project_root

from .file_gateway import LocalFileGatewayAdapter

MANIFEST_SCHEMA_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_artifact_path(path: str) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        try:
            path_obj = path_obj.relative_to(project_root())
        except ValueError:
            return path_obj.as_posix()
    return path_obj.as_posix()


class JsonManifestStoreAdapter:
    def __init__(
        self,
        *,
        schema_path: str = "contracts/artifacts/model_manifest.schema.json",
        file_gateway: FileGatewayPort | None = None,
    ) -> None:
        self._schema_path = schema_path
        self._file_gateway = file_gateway or LocalFileGatewayAdapter()

    def build_manifest(
        self,
        model_type: str,
        artifact_path: str,
        feature_names: list[str],
        cat_features: list[str],
        train_window: dict[str, int],
        metrics: dict[str, float | None],
        source_table: str,
        note: str | None,
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "model_type": model_type,
            "artifact_path": _normalize_artifact_path(artifact_path),
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "feature_names": list(feature_names),
            "cat_features": list(cat_features),
            "train_window": {
                "train_year_start": int(train_window["train_year_start"]),
                "train_year_end": int(train_window["train_year_end"]),
                "test_year": int(train_window["test_year"]),
            },
            "created_at_utc": _utc_now_iso(),
            "metrics": {
                "auc": metrics.get("auc"),
                "brier": metrics.get("brier"),
                "logloss": metrics.get("logloss"),
            },
            "source_table": source_table,
        }
        if note:
            manifest["note"] = note
        return manifest

    def validate_manifest(self, manifest: dict[str, Any]) -> None:
        schema = json.loads(self._file_gateway.read_text(self._schema_path))
        jsonschema.validate(instance=manifest, schema=schema)

    def write_manifest(self, manifest: dict[str, Any], manifest_out: str) -> None:
        content = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        self._file_gateway.write_text(manifest_out, content)


class JsonManifestReaderAdapter:
    def __init__(self, *, file_gateway: FileGatewayPort | None = None) -> None:
        self._file_gateway = file_gateway or LocalFileGatewayAdapter()

    def read_model_type(self, manifest_path: str) -> str | None:
        if not self._file_gateway.exists(manifest_path):
            raise FileNotFoundError(f"manifest file not found: {manifest_path}")
        manifest = json.loads(self._file_gateway.read_text(manifest_path))
        model_type = manifest.get("model_type")
        if isinstance(model_type, str) and model_type.strip():
            return model_type.strip()
        return None
