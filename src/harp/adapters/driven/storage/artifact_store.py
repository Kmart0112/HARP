from __future__ import annotations

import io
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from harp.interface.ports import FileGatewayPort

from .file_gateway import LocalFileGatewayAdapter


ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class _LegacyArtifactBridge:
    version: int = 0
    created_at_utc: str = ""
    payload: dict[str, Any] | None = None


class _CompatUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in {
            ("src.modeling.artifacts", "Artifact"),
            ("harp.inference.artifact_loader", "Artifact"),
        }:
            return _LegacyArtifactBridge
        return super().find_class(module, name)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_payload(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        payload = obj.get("payload")
        if isinstance(payload, dict):
            return payload
        return obj

    payload = getattr(obj, "payload", None)
    if isinstance(payload, dict):
        return payload

    raise TypeError(f"Unsupported artifact format: {type(obj)}")


class PickleArtifactStoreAdapter:
    def __init__(self, *, file_gateway: FileGatewayPort | None = None) -> None:
        self._file_gateway = file_gateway or LocalFileGatewayAdapter()

    def save_artifact(self, payload: dict[str, Any], artifact_out: str) -> None:
        artifact = {
            "version": ARTIFACT_VERSION,
            "created_at_utc": _utc_now_iso(),
            "payload": payload,
        }
        data = pickle.dumps(artifact, protocol=pickle.HIGHEST_PROTOCOL)
        self._file_gateway.write_bytes(artifact_out, data)

    def copy_legacy(self, src: str, dst: str, enabled: bool) -> str | None:
        if not enabled:
            return None

        if not self._file_gateway.exists(src):
            raise FileNotFoundError(f"artifact copy source not found: {src}")

        self._file_gateway.copy(src, dst)
        return dst


class PickleModelLoaderAdapter:
    def __init__(self, *, file_gateway: FileGatewayPort | None = None) -> None:
        self._file_gateway = file_gateway or LocalFileGatewayAdapter()

    def load_model_payload(self, path: str) -> dict[str, Any]:
        if not self._file_gateway.exists(path):
            raise FileNotFoundError(f"Artifact file not found: {path}")

        raw = self._file_gateway.read_bytes(path)
        obj = _CompatUnpickler(io.BytesIO(raw)).load()

        payload = _extract_payload(obj)
        if "model" not in payload:
            raise KeyError("Artifact payload does not include 'model'.")
        if "feature_names" not in payload:
            raise KeyError("Artifact payload does not include 'feature_names'.")
        return payload
