from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TrackingRunRecord:
    run_id: str
    run_name: str
    status: str
    start_time: int | None
    end_time: int | None
    params: dict[str, str]
    metrics: dict[str, float]
    tags: dict[str, str]


class TrackingPort(Protocol):
    def start_run(
        self,
        experiment_name: str,
        run_name: str,
        tags: dict[str, str] | None = None,
        parent_run_id: str | None = None,
    ) -> str:
        ...

    def log_params(self, run_id: str, params: dict[str, object]) -> None:
        ...

    def log_tags(self, run_id: str, tags: dict[str, str]) -> None:
        ...

    def log_metrics(
        self,
        run_id: str,
        metrics: dict[str, float],
        step: int | None = None,
    ) -> None:
        ...

    def log_artifact(
        self,
        run_id: str,
        local_path: str,
        artifact_path: str | None = None,
    ) -> None:
        ...

    def log_artifacts(
        self,
        run_id: str,
        local_dir: str,
        artifact_path: str | None = None,
    ) -> None:
        ...

    def log_dict(
        self,
        run_id: str,
        payload: dict[str, object],
        artifact_file: str,
    ) -> None:
        ...

    def get_run(self, run_id: str) -> TrackingRunRecord:
        ...

    def list_child_runs(self, parent_run_id: str) -> tuple[TrackingRunRecord, ...]:
        ...

    def read_dict_artifact(self, run_id: str, artifact_file: str) -> dict[str, object]:
        ...

    def set_terminated(self, run_id: str, status: str) -> None:
        ...
