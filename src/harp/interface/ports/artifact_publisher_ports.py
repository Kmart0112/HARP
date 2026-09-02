from __future__ import annotations

from typing import Protocol


class ParentArtifactPublisherPort(Protocol):
    def publish_parent_artifacts(
        self,
        *,
        parent_run_id: str,
        run_log_dir: str,
        theme_revision: int,
        latest_artifacts: dict[str, str],
        revision_artifacts: dict[str, str],
        summary: dict[str, object],
    ) -> None:
        ...
