from __future__ import annotations

from pathlib import Path

from harp.interface.ports import FileGatewayPort, TrackingPort


class TrackingParentArtifactPublisherAdapter:
    def __init__(
        self,
        *,
        file_gateway: FileGatewayPort,
        tracking: TrackingPort,
    ) -> None:
        self._file_gateway = file_gateway
        self._tracking = tracking

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
        latest_dir = Path(run_log_dir) / "parent_artifacts" / "latest"
        revision_dir = Path(run_log_dir) / "parent_artifacts" / "revisions" / str(theme_revision)

        for name, src in latest_artifacts.items():
            dst = str(latest_dir / name)
            self._file_gateway.copy(src, dst)
            self._tracking.log_artifact(parent_run_id, dst, artifact_path="reports")

        for name, src in revision_artifacts.items():
            dst = str(revision_dir / name)
            self._file_gateway.copy(src, dst)
            self._tracking.log_artifact(parent_run_id, dst, artifact_path=f"revisions/{theme_revision}")

        self._tracking.log_dict(parent_run_id, summary, artifact_file="summary.json")
        self._tracking.log_dict(parent_run_id, summary, artifact_file=f"revisions/{theme_revision}/summary.json")
