from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MlflowStoreVerification:
    experiment_names: tuple[str, ...]


class MlflowStorePort(Protocol):
    def resolve_local_store_dir(self, tracking_uri: str) -> str | None:
        ...

    def verify_store_readable(self, tracking_uri: str) -> MlflowStoreVerification:
        ...

    def detect_legacy_path_references(
        self,
        *,
        tracking_uri: str,
        legacy_store_dir: str,
    ) -> tuple[str, ...]:
        ...

    def rewrite_meta_for_target(
        self,
        *,
        rel_path: str,
        source_text: str,
        target_store_dir: str,
    ) -> str:
        ...
