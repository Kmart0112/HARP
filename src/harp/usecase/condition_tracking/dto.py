from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import (
    ConditionSplitReportReaderPort,
    ConditionTrackingPublisherPort,
)


@dataclass(frozen=True)
class ConditionSplitCompareTrackingRequest:
    experiment_name: str
    run_name: str
    summary_csv_path: str
    slices_csv_path: str
    parent_run_id: str | None = None
    tags: dict[str, str] | None = None


@dataclass(frozen=True)
class ConditionSplitCompareTrackingDeps:
    report_reader: ConditionSplitReportReaderPort
    publisher: ConditionTrackingPublisherPort


@dataclass(frozen=True)
class ConditionSplitCompareTrackingResult:
    experiment_name: str
    run_name: str
    run_id: str
    summary_csv_path: str
    slices_csv_path: str
    slice_count: int
    param_keys: tuple[str, ...]
    metric_keys: tuple[str, ...]
