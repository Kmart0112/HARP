from __future__ import annotations

from typing import Any, Protocol


class ArtifactStorePort(Protocol):
    def save_artifact(
        self,
        payload: dict[str, Any],
        artifact_out: str,
    ) -> None:
        ...

    def copy_legacy(
        self,
        src: str,
        dst: str,
        enabled: bool,
    ) -> str | None:
        ...


class ManifestStorePort(Protocol):
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
        ...

    def validate_manifest(self, manifest: dict[str, Any]) -> None:
        ...

    def write_manifest(
        self,
        manifest: dict[str, Any],
        manifest_out: str,
    ) -> None:
        ...


class ManifestReaderPort(Protocol):
    def read_model_type(self, manifest_path: str) -> str | None:
        ...
