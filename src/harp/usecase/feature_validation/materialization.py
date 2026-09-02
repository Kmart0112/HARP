from __future__ import annotations

from dataclasses import dataclass

from .dto import FeatureValidationDeps, FeatureValidationRequest, ValidationScenarioResult
from .reporting import build_parent_summary, build_report_model, render_report_markdown, render_runs_csv
from .scenarios import materialize_report_images


@dataclass(frozen=True)
class MaterializedFeatureValidationOutputs:
    scenario_results: tuple[ValidationScenarioResult, ...]
    theme_status: str
    summary: dict[str, object]


def materialize_feature_validation_outputs(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
    parent_run_id: str,
    theme_revision: int,
    append_history: tuple[str, ...],
    report_out: str,
    runs_csv_out: str,
    run_log_dir: str,
    scenario_results: tuple[ValidationScenarioResult, ...],
) -> MaterializedFeatureValidationOutputs:
    scenario_results = materialize_report_images(
        report_out=report_out,
        file_gateway=deps.file_gateway,
        scenario_results=scenario_results,
    )
    deps.file_gateway.write_text(runs_csv_out, render_runs_csv(list(scenario_results)))
    report_model = build_report_model(req=req, scenario_results=scenario_results)
    report_body = render_report_markdown(
        req=req,
        report_model=report_model,
        parent_run_id=parent_run_id,
        theme_revision=theme_revision,
        append_history=append_history,
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        run_log_dir=run_log_dir,
        scenario_results=scenario_results,
    )
    deps.file_gateway.write_text(report_out, report_body)
    theme_status = "finalized" if req.finalize else "open"
    summary = build_parent_summary(
        req=req,
        report_model=report_model,
        parent_run_id=parent_run_id,
        scenario_results=list(scenario_results),
        theme_status=theme_status,
        theme_revision=theme_revision,
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        run_log_dir=run_log_dir,
        append_history=append_history,
    )
    return MaterializedFeatureValidationOutputs(
        scenario_results=scenario_results,
        theme_status=theme_status,
        summary=summary,
    )
