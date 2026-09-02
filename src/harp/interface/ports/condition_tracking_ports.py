from __future__ import annotations

from typing import Protocol

from harp.core.condition_tracking import ConditionSplitReport, ConditionTrackingPayload


class ConditionSplitReportReaderPort(Protocol):
    def read_report(self, *, summary_csv_path: str, slices_csv_path: str) -> ConditionSplitReport:
        ...


class ConditionTrackingPublisherPort(Protocol):
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
        ...
