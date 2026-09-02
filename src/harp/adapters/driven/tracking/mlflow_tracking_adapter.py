from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from harp.interface.ports import TrackingRunRecord
from harp.shared.paths import project_root

from .local_mlflow_store_adapter import LocalMlflowStoreAdapter


_MLFLOW_PARENT_RUN_TAG = "mlflow.parentRunId"


def _normalize_param_value(value: object) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class MlflowTrackingAdapter:
    def __init__(self, *, tracking_uri: str) -> None:
        self._tracking_uri = tracking_uri
        self._store_adapter = LocalMlflowStoreAdapter()
        self._consistency_checked = False

    def _ensure_local_store_consistency(self) -> None:
        if self._consistency_checked:
            return
        resolved_store_dir = self._store_adapter.resolve_local_store_dir(self._tracking_uri)
        if resolved_store_dir is None:
            self._consistency_checked = True
            return
        legacy_store_dir = str((project_root() / "notebook" / "tmp" / "mlflow").resolve())
        stale_meta_files = self._store_adapter.detect_legacy_path_references(
            tracking_uri=self._tracking_uri,
            legacy_store_dir=legacy_store_dir,
        )
        if stale_meta_files:
            raise ValueError(
                "MLflow store metadata still references the legacy notebook/tmp/mlflow path. "
                "Run `uv run python -m pipeline.jobs.migrate_mlflow_store` before using this tracking store."
            )
        self._consistency_checked = True

    @contextmanager
    def _run_context(self, run_id: str) -> Iterator[None]:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        with mlflow.start_run(run_id=run_id):
            yield

    def start_run(
        self,
        experiment_name: str,
        run_name: str,
        tags: dict[str, str] | None = None,
        parent_run_id: str | None = None,
    ) -> str:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        experiment = mlflow.set_experiment(experiment_name)
        resolved_tags = dict(tags or {})
        if parent_run_id:
            resolved_tags[_MLFLOW_PARENT_RUN_TAG] = parent_run_id

        with mlflow.start_run(
            experiment_id=experiment.experiment_id,
            run_name=run_name,
            nested=bool(parent_run_id),
            tags=resolved_tags or None,
        ) as run:
            return run.info.run_id

    def log_params(self, run_id: str, params: dict[str, object]) -> None:
        import mlflow

        normalized = {key: _normalize_param_value(value) for key, value in params.items()}
        with self._run_context(run_id):
            mlflow.log_params(normalized)

    def log_tags(self, run_id: str, tags: dict[str, str]) -> None:
        import mlflow

        with self._run_context(run_id):
            mlflow.set_tags(tags)

    def log_metrics(
        self,
        run_id: str,
        metrics: dict[str, float],
        step: int | None = None,
    ) -> None:
        import mlflow

        with self._run_context(run_id):
            mlflow.log_metrics(metrics, step=step)

    def log_artifact(
        self,
        run_id: str,
        local_path: str,
        artifact_path: str | None = None,
    ) -> None:
        import mlflow

        with self._run_context(run_id):
            mlflow.log_artifact(local_path, artifact_path=artifact_path)

    def log_artifacts(
        self,
        run_id: str,
        local_dir: str,
        artifact_path: str | None = None,
    ) -> None:
        import mlflow

        with self._run_context(run_id):
            mlflow.log_artifacts(local_dir, artifact_path=artifact_path)

    def log_dict(
        self,
        run_id: str,
        payload: dict[str, object],
        artifact_file: str,
    ) -> None:
        import mlflow

        with self._run_context(run_id):
            mlflow.log_dict(payload, artifact_file)

    def get_run(self, run_id: str) -> TrackingRunRecord:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        client = mlflow.tracking.MlflowClient(tracking_uri=self._tracking_uri)
        return _to_tracking_run_record(client.get_run(run_id))

    def list_child_runs(self, parent_run_id: str) -> tuple[TrackingRunRecord, ...]:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        client = mlflow.tracking.MlflowClient(tracking_uri=self._tracking_uri)
        parent = client.get_run(parent_run_id)
        experiment_id = parent.info.experiment_id
        runs = client.search_runs(
            experiment_ids=[experiment_id],
            filter_string=f"tags.`{_MLFLOW_PARENT_RUN_TAG}` = '{parent_run_id}'",
            order_by=["attributes.start_time ASC"],
        )
        return tuple(_to_tracking_run_record(run) for run in runs)

    def read_dict_artifact(self, run_id: str, artifact_file: str) -> dict[str, object]:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        client = mlflow.tracking.MlflowClient(tracking_uri=self._tracking_uri)
        local_path = client.download_artifacts(run_id, artifact_file)
        payload = json.loads(Path(local_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"artifact is not a JSON object: run_id={run_id} artifact_file={artifact_file}")
        return payload

    def set_terminated(self, run_id: str, status: str) -> None:
        import mlflow

        self._ensure_local_store_consistency()
        mlflow.set_tracking_uri(self._tracking_uri)
        client = mlflow.tracking.MlflowClient(tracking_uri=self._tracking_uri)
        client.set_terminated(run_id, status=status)


def _to_tracking_run_record(run) -> TrackingRunRecord:  # noqa: ANN001
    return TrackingRunRecord(
        run_id=str(run.info.run_id),
        run_name=str(run.data.tags.get("mlflow.runName", "")),
        status=str(run.info.status),
        start_time=run.info.start_time,
        end_time=run.info.end_time,
        params=dict(run.data.params),
        metrics={str(key): float(value) for key, value in run.data.metrics.items()},
        tags={str(key): str(value) for key, value in run.data.tags.items()},
    )
