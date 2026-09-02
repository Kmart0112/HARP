from __future__ import annotations

import csv

from harp.core.condition_tracking import ConditionSplitReport, ConditionTrackingPayload
from harp.interface.ports import FileGatewayPort, TrackingPort


class CsvConditionSplitReportReaderAdapter:
    def __init__(self, file_gateway: FileGatewayPort) -> None:
        self._file_gateway = file_gateway

    def read_report(self, *, summary_csv_path: str, slices_csv_path: str) -> ConditionSplitReport:
        if not self._file_gateway.exists(summary_csv_path):
            raise FileNotFoundError(f"summary csv not found: {summary_csv_path}")
        if not self._file_gateway.exists(slices_csv_path):
            raise FileNotFoundError(f"slices csv not found: {slices_csv_path}")
        summary_rows = self._read_rows(summary_csv_path)
        if len(summary_rows) != 1:
            raise ValueError(f"summary csv must contain exactly one row: {summary_csv_path}")
        return ConditionSplitReport(
            summary_row=summary_rows[0],
            slice_rows=tuple(self._read_rows(slices_csv_path)),
        )

    def _read_rows(self, path: str) -> list[dict[str, str]]:
        reader = csv.DictReader(self._file_gateway.read_text(path).splitlines())
        return [dict(row) for row in reader]


class TrackingConditionPublisherAdapter:
    def __init__(self, tracking: TrackingPort) -> None:
        self._tracking = tracking

    def publish(
        self,
        *,
        experiment_name: str,
        run_name: str,
        parent_run_id: str | None,
        summary_csv_path: str,
        slices_csv_path: str,
        payload: ConditionTrackingPayload,
    ) -> str:
        run_id: str | None = None
        try:
            run_id = self._tracking.start_run(
                experiment_name=experiment_name,
                run_name=run_name,
                tags=payload.tags,
                parent_run_id=parent_run_id,
            )
            self._tracking.log_params(run_id, payload.params)
            self._tracking.log_metrics(run_id, payload.metrics)
            self._tracking.log_artifact(run_id, summary_csv_path, artifact_path="condition_split_compare")
            self._tracking.log_artifact(run_id, slices_csv_path, artifact_path="condition_split_compare")
            self._tracking.log_dict(
                run_id,
                payload.summary,
                artifact_file="condition_split_compare/summary.json",
            )
            self._tracking.set_terminated(run_id, status="FINISHED")
        except Exception:
            if run_id is not None:
                self._tracking.set_terminated(run_id, status="FAILED")
            raise
        assert run_id is not None
        return run_id
