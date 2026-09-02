from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ConditionSplitReport:
    summary_row: dict[str, str]
    slice_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ConditionTrackingPayload:
    params: dict[str, object]
    metrics: dict[str, float]
    tags: dict[str, str]
    summary: dict[str, object]


def build_condition_tracking_payload(
    *,
    report: ConditionSplitReport,
    experiment_name: str,
    run_name: str,
    summary_csv_path: str,
    slices_csv_path: str,
    parent_run_id: str | None,
    extra_tags: dict[str, str] | None,
) -> ConditionTrackingPayload:
    summary_row = report.summary_row
    slice_rows = report.slice_rows
    params: dict[str, object] = {
        "condition_column": summary_row.get("condition_column", ""),
        "split_mode": summary_row.get("split_mode", ""),
        "primary_metric": summary_row.get("primary_metric", ""),
        "summary_csv_path": summary_csv_path,
        "slices_csv_path": slices_csv_path,
        "slice_count": len(slice_rows),
    }
    if parent_run_id:
        params["parent_run_id"] = parent_run_id

    metrics: dict[str, float] = {}
    for key, raw_value in summary_row.items():
        if key in {"condition_column", "split_mode", "primary_metric"}:
            continue
        value = _coerce_float(raw_value)
        if value is not None:
            metrics[key] = value

    tags = {
        "source": "condition_split_compare",
        "condition_column": str(summary_row.get("condition_column", "")),
        "split_mode": str(summary_row.get("split_mode", "")),
        "primary_metric": str(summary_row.get("primary_metric", "")),
    }
    tags.update(extra_tags or {})
    param_keys = tuple(sorted(params))
    metric_keys = tuple(sorted(metrics))
    summary = {
        "experiment_name": experiment_name,
        "run_name": run_name,
        "summary_csv_path": summary_csv_path,
        "slices_csv_path": slices_csv_path,
        "summary": summary_row,
        "slice_count": len(slice_rows),
        "slice_preview": list(slice_rows[:3]),
        "param_keys": list(param_keys),
        "metric_keys": list(metric_keys),
    }
    return ConditionTrackingPayload(
        params=params,
        metrics=metrics,
        tags=tags,
        summary=summary,
    )


def _coerce_float(raw_value: str) -> float | None:
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value
