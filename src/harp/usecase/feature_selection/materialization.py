from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .decisions import build_decisions
from .dto import (
    FeatureSelectionDecisionRow,
    FeatureSelectionDeps,
    FeatureSelectionRequest,
    FeatureSelectionScenarioResult,
)
from .reporting import (
    build_parent_summary,
    render_decisions_csv,
    render_report_markdown,
    render_runs_csv,
)


@dataclass(frozen=True)
class MaterializedFeatureSelectionOutputs:
    decision_rows: tuple[FeatureSelectionDecisionRow, ...]
    final_feature_names: list[str]
    final_cat_features: list[str]
    theme_status: str
    contract_written: bool
    summary: dict[str, object]


def materialize_feature_selection_outputs(
    *,
    req: FeatureSelectionRequest,
    deps: FeatureSelectionDeps,
    parent_run_id: str,
    scenario_results: tuple[FeatureSelectionScenarioResult, ...],
    base_feature_names: list[str],
    base_cat_features: list[str],
    report_out: str,
    runs_csv_out: str,
    decisions_csv_out: str,
    selected_contract_snapshot_out: str,
    target_contract_path: str,
    run_log_dir: str,
    append_history: tuple[str, ...],
    theme_revision: int,
    auc_threshold: float,
    logloss_threshold: float,
) -> MaterializedFeatureSelectionOutputs:
    decision_rows, final_feature_names, final_cat_features = build_decisions(
        req=req,
        scenario_results=scenario_results,
        base_feature_names=base_feature_names,
        base_cat_features=base_cat_features,
        auc_threshold=auc_threshold,
        logloss_threshold=logloss_threshold,
    )
    if req.finalize and any(row.unresolved for row in decision_rows):
        raise ValueError("cannot finalize feature_selection theme with unresolved decisions.")

    selected_contract_yaml = render_contract_yaml(
        feature_definition_port=deps.feature_definition_port,
        contract_name=Path(target_contract_path).stem,
        feature_names=final_feature_names,
        cat_features=final_cat_features,
    )
    deps.file_gateway.write_text(decisions_csv_out, render_decisions_csv(decision_rows))
    deps.file_gateway.write_text(runs_csv_out, render_runs_csv(scenario_results))
    deps.file_gateway.write_text(selected_contract_snapshot_out, selected_contract_yaml)

    contract_written = False
    if req.finalize and req.write_contract:
        deps.file_gateway.write_text(target_contract_path, selected_contract_yaml)
        contract_written = True

    report_body = render_report_markdown(
        req=req,
        parent_run_id=parent_run_id,
        theme_revision=theme_revision,
        append_history=append_history,
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        decisions_csv_out=decisions_csv_out,
        selected_contract_snapshot_out=selected_contract_snapshot_out,
        target_contract_path=target_contract_path,
        contract_written=contract_written,
        scenario_results=scenario_results,
        decision_rows=decision_rows,
        base_feature_names=base_feature_names,
        final_feature_names=final_feature_names,
        auc_threshold=auc_threshold,
        logloss_threshold=logloss_threshold,
    )
    deps.file_gateway.write_text(report_out, report_body)

    theme_status = "finalized" if req.finalize else "open"
    summary = build_parent_summary(
        req=req,
        parent_run_id=parent_run_id,
        theme_status=theme_status,
        theme_revision=theme_revision,
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        decisions_csv_out=decisions_csv_out,
        selected_contract_snapshot_out=selected_contract_snapshot_out,
        target_contract_path=target_contract_path,
        run_log_dir=run_log_dir,
        append_history=append_history,
        scenario_results=scenario_results,
        decision_rows=decision_rows,
        final_feature_names=final_feature_names,
        final_cat_features=final_cat_features,
        contract_written=contract_written,
    )

    return MaterializedFeatureSelectionOutputs(
        decision_rows=decision_rows,
        final_feature_names=final_feature_names,
        final_cat_features=final_cat_features,
        theme_status=theme_status,
        contract_written=contract_written,
        summary=summary,
    )


def render_contract_yaml(
    *,
    feature_definition_port,
    contract_name: str,
    feature_names: list[str],
    cat_features: list[str],
) -> str:
    return feature_definition_port.render_contract(
        contract_name=contract_name,
        feature_names=feature_names,
        cat_features=cat_features,
    )


def write_base_contract_snapshot(req: FeatureSelectionRequest, deps: FeatureSelectionDeps) -> str:
    source_path = resolve_feature_set_contract_source_path(
        feature_definition_port=deps.feature_definition_port,
        contract_path=req.feature_sets_path,
        feature_set_name=req.base_feature_set_name,
    )
    snapshot_path = str(Path(req.run_log_dir) / "inputs" / "base_feature_set_contract.yml")
    deps.file_gateway.write_text(snapshot_path, deps.file_gateway.read_text(source_path))
    return snapshot_path


def resolve_feature_set_contract_source_path(
    *,
    feature_definition_port,
    contract_path: str,
    feature_set_name: str,
) -> str:
    return feature_definition_port.find_contract_path(
        contract_dir=contract_path,
        feature_set_name=feature_set_name,
    )
