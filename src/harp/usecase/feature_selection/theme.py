from __future__ import annotations

from ..theme_tracking import (
    ThemeRunState,
    collect_latest_child_summaries,
    load_theme_state,
    sync_attempt_statuses,
)
from .dto import FeatureSelectionDeps, FeatureSelectionRequest, FeatureSelectionScenarioResult
from .reconstruction import normalize_effective_results, scenario_result_from_summary
from .scenarios import ScenarioSpec


def build_parent_tags(
    *,
    req: FeatureSelectionRequest,
    report_out: str,
    runs_csv_out: str,
    decisions_csv_out: str,
    selected_contract_snapshot_out: str,
    target_contract_path: str,
    theme_status: str,
    theme_revision: int,
) -> dict[str, str]:
    return {
        "run_role": "parent",
        "category": req.category,
        "theme_kind": "feature_selection",
        "theme_name": req.validation_name,
        "preset_name": req.preset_name,
        "git_commit": req.git_commit,
        "report_path": report_out,
        "runs_csv_path": runs_csv_out,
        "decisions_csv_path": decisions_csv_out,
        "selected_contract_snapshot_path": selected_contract_snapshot_out,
        "target_contract_path": target_contract_path,
        "theme_status": theme_status,
        "theme_revision": str(theme_revision),
    }


def load_feature_selection_theme_state(
    *,
    req: FeatureSelectionRequest,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
) -> ThemeRunState[FeatureSelectionScenarioResult]:
    return load_theme_state(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        expected_theme_kind="feature_selection",
        expected_identity_tags={
            "theme_name": req.validation_name,
            "preset_name": req.preset_name,
        },
        fallback_paths={
            "report_path": req.report_out,
            "runs_csv_path": req.runs_csv_out,
            "decisions_csv_path": req.decisions_csv_out,
            "selected_contract_snapshot_path": req.selected_contract_snapshot_out,
            "target_contract_path": req.target_contract_path,
            "run_log_dir": req.run_log_dir,
        },
        result_loader=lambda summary, run_id: scenario_result_from_summary(run_id, summary),
        scenario_name_resolver=lambda summary, child_run: str(
            summary.get("scenario_name") or child_run.tags.get("scenario_name") or child_run.run_name
        ),
    )


def collect_effective_results(
    *,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
    scenarios: tuple[ScenarioSpec, ...],
) -> tuple[FeatureSelectionScenarioResult, ...]:
    result_by_name = collect_latest_child_summaries(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        result_loader=lambda summary, run_id: scenario_result_from_summary(run_id, summary),
        scenario_name_resolver=lambda summary, child_run: str(
            summary.get("scenario_name") or child_run.tags.get("scenario_name") or child_run.run_name
        ),
    )
    return normalize_effective_results(scenarios=scenarios, result_by_name=result_by_name)


def sync_effective_attempt_statuses(
    *,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
    scenarios: tuple[ScenarioSpec, ...],
    effective_results: tuple[FeatureSelectionScenarioResult, ...],
) -> None:
    sync_attempt_statuses(
        tracking=deps.tracking_port,
        parent_run_id=parent_run_id,
        scenario_names={scenario.scenario_name for scenario in scenarios},
        effective_run_ids={result.scenario_run_id for result in effective_results},
    )


def publish_feature_selection_parent_artifacts(
    *,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
    report_out: str,
    runs_csv_out: str,
    decisions_csv_out: str,
    selected_contract_snapshot_out: str,
    theme_revision: int,
    summary: dict[str, object],
    run_log_dir: str,
) -> None:
    deps.parent_artifact_publisher.publish_parent_artifacts(
        parent_run_id=parent_run_id,
        run_log_dir=run_log_dir,
        theme_revision=theme_revision,
        latest_artifacts={
            "report.md": report_out,
            "runs.csv": runs_csv_out,
            "decisions.csv": decisions_csv_out,
            "selected_contract.yml": selected_contract_snapshot_out,
        },
        revision_artifacts={
            "report.md": report_out,
            "runs.csv": runs_csv_out,
            "decisions.csv": decisions_csv_out,
            "selected_contract.yml": selected_contract_snapshot_out,
        },
        summary=summary,
    )
