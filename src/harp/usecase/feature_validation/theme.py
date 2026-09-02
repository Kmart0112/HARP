from __future__ import annotations

from ..theme_tracking import (
    ThemeRunState,
    collect_latest_child_summaries,
    load_theme_state,
    sync_attempt_statuses,
)
from .dto import FeatureValidationDeps, FeatureValidationRequest, ValidationScenarioResult
from .reconstruction import normalize_effective_results, result_from_summary


def build_parent_tags(
    *,
    req: FeatureValidationRequest,
    report_out: str,
    runs_csv_out: str,
    theme_status: str,
    theme_revision: int,
) -> dict[str, str]:
    return {
        "run_role": "parent",
        "category": req.category,
        "theme_kind": "feature_validation",
        "theme_name": req.validation_name,
        "preset_name": req.preset_name,
        "git_commit": req.git_commit,
        "report_path": report_out,
        "runs_csv_path": runs_csv_out,
        "theme_status": theme_status,
        "theme_revision": str(theme_revision),
    }


def load_feature_validation_theme_state(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
    parent_run_id: str,
) -> ThemeRunState[ValidationScenarioResult]:
    return load_theme_state(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        expected_theme_kind="feature_validation",
        expected_identity_tags={
            "theme_name": req.validation_name,
            "preset_name": req.preset_name,
        },
        fallback_paths={
            "report_path": req.report_out,
            "runs_csv_path": req.runs_csv_out,
            "run_log_dir": req.run_log_dir,
        },
        result_loader=lambda summary, run_id: result_from_summary(run_id, summary),
        scenario_name_resolver=lambda summary, child_run: str(
            summary.get("scenario_name") or child_run.tags.get("scenario_name") or child_run.run_name
        ),
    )


def collect_effective_results(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
    parent_run_id: str,
) -> tuple[ValidationScenarioResult, ...]:
    result_by_name = collect_latest_child_summaries(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        result_loader=lambda summary, run_id: result_from_summary(run_id, summary),
        scenario_name_resolver=lambda summary, child_run: str(
            summary.get("scenario_name") or child_run.tags.get("scenario_name") or child_run.run_name
        ),
    )
    return normalize_effective_results(req=req, result_by_name=result_by_name)


def sync_effective_attempt_statuses(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
    parent_run_id: str,
    effective_results: tuple[ValidationScenarioResult, ...],
) -> None:
    sync_attempt_statuses(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        scenario_names={scenario.scenario_name for scenario in req.scenarios},
        effective_run_ids={result.scenario_run_id for result in effective_results},
    )


def publish_feature_validation_parent_artifacts(
    *,
    deps: FeatureValidationDeps,
    parent_run_id: str,
    report_out: str,
    runs_csv_out: str,
    run_log_dir: str,
    theme_revision: int,
    summary: dict[str, object],
) -> None:
    deps.parent_artifact_publisher.publish_parent_artifacts(
        parent_run_id=parent_run_id,
        run_log_dir=run_log_dir,
        theme_revision=theme_revision,
        latest_artifacts={
            "report.md": report_out,
            "runs.csv": runs_csv_out,
        },
        revision_artifacts={
            "report.md": report_out,
            "runs.csv": runs_csv_out,
        },
        summary=summary,
    )
