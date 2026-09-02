from __future__ import annotations

from harp.core.condition_tracking import build_condition_tracking_payload

from .dto import (
    ConditionSplitCompareTrackingDeps,
    ConditionSplitCompareTrackingRequest,
    ConditionSplitCompareTrackingResult,
)


def run_log_condition_split_compare_usecase(
    req: ConditionSplitCompareTrackingRequest,
    deps: ConditionSplitCompareTrackingDeps,
) -> ConditionSplitCompareTrackingResult:
    report = deps.report_reader.read_report(
        summary_csv_path=req.summary_csv_path,
        slices_csv_path=req.slices_csv_path,
    )
    payload = build_condition_tracking_payload(
        report=report,
        experiment_name=req.experiment_name,
        run_name=req.run_name,
        summary_csv_path=req.summary_csv_path,
        slices_csv_path=req.slices_csv_path,
        parent_run_id=req.parent_run_id,
        extra_tags=req.tags,
    )
    run_id = deps.publisher.publish(
        experiment_name=req.experiment_name,
        run_name=req.run_name,
        parent_run_id=req.parent_run_id,
        summary_csv_path=req.summary_csv_path,
        slices_csv_path=req.slices_csv_path,
        payload=payload,
    )
    return ConditionSplitCompareTrackingResult(
        experiment_name=req.experiment_name,
        run_name=req.run_name,
        run_id=run_id,
        summary_csv_path=req.summary_csv_path,
        slices_csv_path=req.slices_csv_path,
        slice_count=len(report.slice_rows),
        param_keys=tuple(sorted(payload.params)),
        metric_keys=tuple(sorted(payload.metrics)),
    )
