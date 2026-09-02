from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import Mock, create_autospec

from harp.interface.ports import (
    FileGatewayPort,
    ParentArtifactPublisherPort,
    TrackingPort,
    TrackingRunRecord,
)


@dataclass
class FileGatewayState:
    files: dict[str, str] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)


def make_file_gateway_mock(
    initial_files: dict[str, str] | None = None,
) -> tuple[Mock, FileGatewayState]:
    state = FileGatewayState(files=dict(initial_files or {}))
    gateway = create_autospec(FileGatewayPort, instance=True, spec_set=True)

    gateway.exists.side_effect = lambda path: path in state.files or path in state.directories
    gateway.read_text.side_effect = lambda path: state.files[path]
    gateway.read_bytes.side_effect = lambda path: state.files[path].encode("utf-8")
    gateway.write_text.side_effect = lambda path, content: state.files.__setitem__(path, content)
    gateway.write_bytes.side_effect = lambda path, content: state.files.__setitem__(
        path,
        content.decode("utf-8"),
    )
    gateway.copy.side_effect = lambda src, dst: state.files.__setitem__(dst, state.files[src])
    gateway.make_dir.side_effect = lambda path: state.directories.add(path)
    gateway.list_files.side_effect = lambda path: sorted(
        file_path
        for file_path in state.files
        if file_path.startswith(path.rstrip("/") + "/")
    )
    gateway.list_dirs.side_effect = lambda path: sorted(
        directory
        for directory in state.directories
        if directory.startswith(path.rstrip("/") + "/")
    )
    return gateway, state


@dataclass
class TrackingState:
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    dict_artifacts: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)


def make_tracking_port_mock() -> tuple[Mock, TrackingState]:
    state = TrackingState()
    tracking = create_autospec(TrackingPort, instance=True, spec_set=True)

    def start_run(
        experiment_name: str,
        run_name: str,
        tags: dict[str, str] | None = None,
        parent_run_id: str | None = None,
    ) -> str:
        run_id = f"run-{len(state.runs) + 1}"
        state.runs[run_id] = {
            "experiment_name": experiment_name,
            "run_name": run_name,
            "tags": dict(tags or {}),
            "params": {},
            "metrics": {},
            "parent_run_id": parent_run_id,
            "status": "RUNNING",
            "sequence": len(state.runs) + 1,
        }
        return run_id

    def log_params(run_id: str, params: dict[str, object]) -> None:
        state.runs[run_id]["params"].update({key: str(value) for key, value in params.items()})

    def log_tags(run_id: str, tags: dict[str, str]) -> None:
        state.runs[run_id]["tags"].update(tags)

    def log_metrics(run_id: str, metrics: dict[str, float], step: int | None = None) -> None:
        del step
        state.runs[run_id]["metrics"].update({key: float(value) for key, value in metrics.items()})

    def log_dict(run_id: str, payload: dict[str, object], artifact_file: str) -> None:
        state.dict_artifacts[(run_id, artifact_file)] = dict(payload)

    def get_run(run_id: str) -> TrackingRunRecord:
        run = state.runs[run_id]
        return TrackingRunRecord(
            run_id=run_id,
            run_name=str(run["run_name"]),
            status=str(run["status"]),
            start_time=int(run["sequence"]),
            end_time=int(run["sequence"]),
            params=dict(run["params"]),
            metrics=dict(run["metrics"]),
            tags=dict(run["tags"]),
        )

    def list_child_runs(parent_run_id: str) -> tuple[TrackingRunRecord, ...]:
        return tuple(
            get_run(run_id)
            for run_id, run in state.runs.items()
            if run["parent_run_id"] == parent_run_id
        )

    def read_dict_artifact(run_id: str, artifact_file: str) -> dict[str, object]:
        try:
            return dict(state.dict_artifacts[(run_id, artifact_file)])
        except KeyError as exc:
            raise FileNotFoundError(
                f"artifact not found: run_id={run_id} artifact_file={artifact_file}"
            ) from exc

    def set_terminated(run_id: str, status: str) -> None:
        state.runs[run_id]["status"] = status

    tracking.start_run.side_effect = start_run
    tracking.log_params.side_effect = log_params
    tracking.log_tags.side_effect = log_tags
    tracking.log_metrics.side_effect = log_metrics
    tracking.log_dict.side_effect = log_dict
    tracking.get_run.side_effect = get_run
    tracking.list_child_runs.side_effect = list_child_runs
    tracking.read_dict_artifact.side_effect = read_dict_artifact
    tracking.set_terminated.side_effect = set_terminated
    tracking.log_artifact.side_effect = lambda *args, **kwargs: None
    tracking.log_artifacts.side_effect = lambda *args, **kwargs: None
    return tracking, state


def make_parent_artifact_publisher_mock(*, file_gateway: Mock, tracking: Mock) -> Mock:
    publisher = create_autospec(ParentArtifactPublisherPort, instance=True, spec_set=True)

    def publish_parent_artifacts(
        *,
        parent_run_id: str,
        run_log_dir: str,
        theme_revision: int,
        latest_artifacts: dict[str, str],
        revision_artifacts: dict[str, str],
        summary: dict[str, object],
    ) -> None:
        for name, source in latest_artifacts.items():
            destination = str(Path(run_log_dir) / "parent_artifacts" / "latest" / name)
            file_gateway.copy(source, destination)
            tracking.log_artifact(parent_run_id, destination, artifact_path="reports")
        for name, source in revision_artifacts.items():
            destination = str(
                Path(run_log_dir) / "parent_artifacts" / "revisions" / str(theme_revision) / name
            )
            file_gateway.copy(source, destination)
            tracking.log_artifact(
                parent_run_id,
                destination,
                artifact_path=f"revisions/{theme_revision}",
            )
        tracking.log_dict(parent_run_id, summary, artifact_file="summary.json")
        tracking.log_dict(
            parent_run_id,
            summary,
            artifact_file=f"revisions/{theme_revision}/summary.json",
        )

    publisher.publish_parent_artifacts.side_effect = publish_parent_artifacts
    return publisher


def normalized_path(path: str) -> str:
    return str(Path(path))
