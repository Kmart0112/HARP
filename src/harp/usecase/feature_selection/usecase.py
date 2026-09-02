from __future__ import annotations

from ..theme_tracking import (
    ThemeRunState,
    build_attempt_counts,
    terminate_safely,
)
from .dto import (
    FeatureSelectionDeps,
    FeatureSelectionRequest,
    FeatureSelectionResult,
    FeatureSelectionScenarioResult,
)
from .execution import (
    ScenarioExecutionTracker,
    mark_started_scenario_runs_failed,
    run_selection_scenarios,
)
from .materialization import (
    materialize_feature_selection_outputs,
    write_base_contract_snapshot,
)
from .reconstruction import (
    resolve_baseline_metrics,
)
from .scenarios import (
    ScenarioSpec,
    build_scenarios,
)
from .theme import (
    build_parent_tags,
    collect_effective_results,
    load_feature_selection_theme_state,
    publish_feature_selection_parent_artifacts,
    sync_effective_attempt_statuses,
)

_AUC_THRESHOLD = 1e-5
_LOGLOSS_THRESHOLD = -1e-5


def run_feature_selection_usecase(
    req: FeatureSelectionRequest,
    deps: FeatureSelectionDeps,
) -> FeatureSelectionResult:
    _validate_request(req)
    tracking = deps.tracking_port
    base_feature_set = deps.feature_definition_port.load_feature_set(
        source_path=req.feature_sets_path,
        feature_set_name=req.base_feature_set_name,
        mode="production",
    )
    base_feature_names = list(base_feature_set.feature_names)
    base_cat_features = list(base_feature_set.cat_features)
    scenarios = build_scenarios(req)
    selected_scenarios = _select_target_scenarios(req, scenarios)

    parent_run_id: str | None = req.resume_parent_run_id
    scenario_tracker = ScenarioExecutionTracker()
    parent_theme_state: ThemeRunState[FeatureSelectionScenarioResult] | None = None
    report_out = req.report_out
    runs_csv_out = req.runs_csv_out
    decisions_csv_out = req.decisions_csv_out
    selected_contract_snapshot_out = req.selected_contract_snapshot_out
    target_contract_path = req.target_contract_path
    effective_run_log_dir = req.run_log_dir
    append_history: tuple[str, ...] = ()
    theme_revision = 1
    theme_status = "open"
    contract_written = False

    try:
        if req.resume_parent_run_id:
            parent_theme_state = load_feature_selection_theme_state(
                req=req,
                deps=deps,
                parent_run_id=req.resume_parent_run_id,
            )
            parent_run_id = parent_theme_state.parent_run_id
            report_out = parent_theme_state.path_overrides["report_path"]
            runs_csv_out = parent_theme_state.path_overrides["runs_csv_path"]
            decisions_csv_out = parent_theme_state.path_overrides["decisions_csv_path"]
            selected_contract_snapshot_out = parent_theme_state.path_overrides["selected_contract_snapshot_path"]
            target_contract_path = parent_theme_state.path_overrides["target_contract_path"]
            effective_run_log_dir = parent_theme_state.path_overrides["run_log_dir"]
            append_history = parent_theme_state.append_history
            if req.append_note and req.append_note.strip():
                append_history = (*append_history, req.append_note.strip())
            theme_revision = parent_theme_state.theme_revision + 1
        else:
            base_contract_snapshot_path = write_base_contract_snapshot(req, deps)
            append_history = ((req.append_note or "").strip(),) if (req.append_note or "").strip() else ()
            parent_run_id = tracking.start_run(
                experiment_name=req.experiment_name,
                run_name=req.validation_name,
                tags=build_parent_tags(
                    req=req,
                    report_out=report_out,
                    runs_csv_out=runs_csv_out,
                    decisions_csv_out=decisions_csv_out,
                    selected_contract_snapshot_out=selected_contract_snapshot_out,
                    target_contract_path=target_contract_path,
                    theme_status="open",
                    theme_revision=theme_revision,
                ),
            )
            tracking.log_params(
                parent_run_id,
                {
                    "validation_name": req.validation_name,
                    "category": req.category,
                    "change_summary": req.change_summary,
                    "command": req.command,
                    "base_feature_set_name": req.base_feature_set_name,
                    "target_contract_path": target_contract_path,
                    "preset_name": req.preset_name,
                },
            )
            tracking.log_artifact(parent_run_id, base_contract_snapshot_path, artifact_path="inputs")

        assert parent_run_id is not None

        existing_results = ()
        if parent_theme_state is not None:
            existing_results = parent_theme_state.effective_results
        baseline_metrics = resolve_baseline_metrics(existing_results, selected_scenarios)
        if baseline_metrics is None and selected_scenarios and selected_scenarios[0].scenario_name != "baseline_existing":
            raise ValueError("baseline_existing must be available before rerunning non-baseline scenarios.")

        attempt_counts = build_attempt_counts(parent_theme_state)
        run_selection_scenarios(
            req=req,
            deps=deps,
            parent_run_id=parent_run_id,
            selected_scenarios=selected_scenarios,
            base_feature_names=base_feature_names,
            base_cat_features=base_cat_features,
            run_log_dir=effective_run_log_dir,
            initial_baseline_metrics=baseline_metrics,
            attempt_counts=attempt_counts,
            tracker=scenario_tracker,
        )

        scenario_results = collect_effective_results(
            deps=deps,
            parent_run_id=parent_run_id,
            scenarios=scenarios,
        )
        sync_effective_attempt_statuses(
            deps=deps,
            parent_run_id=parent_run_id,
            scenarios=scenarios,
            effective_results=scenario_results,
        )
        materialized_outputs = materialize_feature_selection_outputs(
            req=req,
            deps=deps,
            parent_run_id=parent_run_id,
            scenario_results=scenario_results,
            base_feature_names=base_feature_names,
            base_cat_features=base_cat_features,
            report_out=report_out,
            runs_csv_out=runs_csv_out,
            decisions_csv_out=decisions_csv_out,
            selected_contract_snapshot_out=selected_contract_snapshot_out,
            target_contract_path=target_contract_path,
            run_log_dir=effective_run_log_dir,
            append_history=append_history,
            theme_revision=theme_revision,
            auc_threshold=_AUC_THRESHOLD,
            logloss_threshold=_LOGLOSS_THRESHOLD,
        )
        theme_status = materialized_outputs.theme_status
        contract_written = materialized_outputs.contract_written
        publish_feature_selection_parent_artifacts(
            deps=deps,
            parent_run_id=parent_run_id,
            report_out=report_out,
            runs_csv_out=runs_csv_out,
            decisions_csv_out=decisions_csv_out,
            selected_contract_snapshot_out=selected_contract_snapshot_out,
            run_log_dir=effective_run_log_dir,
            theme_revision=theme_revision,
            summary=materialized_outputs.summary,
        )
        tracking.log_tags(
            parent_run_id,
            {
                "decision": "completed",
                **build_parent_tags(
                    req=req,
                    report_out=report_out,
                    runs_csv_out=runs_csv_out,
                    decisions_csv_out=decisions_csv_out,
                    selected_contract_snapshot_out=selected_contract_snapshot_out,
                    target_contract_path=target_contract_path,
                    theme_status=theme_status,
                    theme_revision=theme_revision,
                ),
            },
        )
        tracking.set_terminated(parent_run_id, status="FINISHED")

        return FeatureSelectionResult(
            validation_name=req.validation_name,
            theme_status=theme_status,
            theme_revision=theme_revision,
            report_path=report_out,
            runs_csv_path=runs_csv_out,
            decisions_csv_path=decisions_csv_out,
            selected_contract_snapshot_path=selected_contract_snapshot_out,
            target_contract_path=target_contract_path,
            contract_written=contract_written,
            run_log_dir=effective_run_log_dir,
            parent_run_id=parent_run_id,
            scenario_run_ids={result.scenario_name: result.scenario_run_id for result in scenario_results},
            effective_scenario_run_ids={result.scenario_name: result.scenario_run_id for result in scenario_results},
            new_scenario_run_ids=dict(scenario_tracker.new_scenario_run_ids),
            scenario_results=scenario_results,
            decisions=materialized_outputs.decision_rows,
        )
    except Exception:
        mark_started_scenario_runs_failed(tracking=tracking, tracker=scenario_tracker)
        if req.resume_parent_run_id is None:
            if parent_run_id is not None:
                try:
                    tracking.log_tags(parent_run_id, {"theme_status": "failed"})
                except Exception:
                    pass
            terminate_safely(tracking, parent_run_id, "FAILED")
        raise


def _validate_request(req: FeatureSelectionRequest) -> None:
    if not req.validation_name.strip():
        raise ValueError("validation_name is required.")
    if not req.aggregate_groups and not req.variant_groups:
        raise ValueError("at least one aggregate_groups or variant_groups entry is required.")
    if req.finalize and not req.write_contract:
        raise ValueError("finalize requires write_contract.")
    if req.write_contract and not req.finalize:
        raise ValueError("write_contract requires finalize.")


def _select_target_scenarios(
    req: FeatureSelectionRequest,
    scenarios: tuple[ScenarioSpec, ...],
) -> tuple[ScenarioSpec, ...]:
    if not req.scenario_filter:
        return scenarios
    requested = set(req.scenario_filter)
    resolved = tuple(scenario for scenario in scenarios if scenario.scenario_name in requested)
    found = {scenario.scenario_name for scenario in resolved}
    missing = requested - found
    if missing:
        raise ValueError(f"scenario_filter contains unknown scenarios: {sorted(missing)}")
    return resolved
