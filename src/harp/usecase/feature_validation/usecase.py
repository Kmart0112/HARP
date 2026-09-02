from __future__ import annotations

from harp.shared.logging import get_logger

from ..theme_tracking import ThemeRunState, build_attempt_counts, terminate_safely
from .config_editing import (
    ensure_required_feature_lines_present,
    write_original_snapshot,
)
from .dto import (
    FeatureValidationDeps,
    FeatureValidationRequest,
    FeatureValidationResult,
    ValidationScenarioResult,
    ValidationScenarioSpec,
)
from .execution import (
    ScenarioExecutionTracker,
    mark_started_scenario_runs_failed,
    run_validation_scenarios,
)
from .materialization import materialize_feature_validation_outputs
from .reconstruction import resolve_baseline_metrics
from .theme import (
    build_parent_tags,
    collect_effective_results,
    load_feature_validation_theme_state,
    publish_feature_validation_parent_artifacts,
    sync_effective_attempt_statuses,
)

logger = get_logger(__name__)


def run_feature_validation_usecase(
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
) -> FeatureValidationResult:
    _validate_request(req)
    tracking = deps.tracking_port
    original_text = _load_original_features_text(req=req, deps=deps)

    selected_scenarios = _select_target_scenarios(req)
    parent_run_id: str | None = req.resume_parent_run_id
    scenario_tracker = ScenarioExecutionTracker()
    restored_features_state = True
    parent_theme_state: ThemeRunState[ValidationScenarioResult] | None = None
    report_out = req.report_out
    runs_csv_out = req.runs_csv_out
    effective_run_log_dir = req.run_log_dir
    append_history: tuple[str, ...] = ()
    theme_revision = 1
    theme_status = "open"

    try:
        if any(scenario.feature_set_diff is None for scenario in selected_scenarios):
            ensure_required_feature_lines_present(original_text, selected_scenarios)

        if req.resume_parent_run_id:
            parent_theme_state = load_feature_validation_theme_state(
                req=req,
                deps=deps,
                parent_run_id=req.resume_parent_run_id,
            )
            parent_run_id = parent_theme_state.parent_run_id
            report_out = parent_theme_state.path_overrides["report_path"]
            runs_csv_out = parent_theme_state.path_overrides["runs_csv_path"]
            effective_run_log_dir = parent_theme_state.path_overrides["run_log_dir"]
            append_history = parent_theme_state.append_history
            if req.append_note and req.append_note.strip():
                append_history = (*append_history, req.append_note.strip())
            theme_revision = parent_theme_state.theme_revision + 1
        else:
            append_history = ((req.append_note or "").strip(),) if (req.append_note or "").strip() else ()
            snapshot_path = write_original_snapshot(
                run_log_dir=effective_run_log_dir,
                file_gateway=deps.file_gateway,
                original_text=original_text,
            )
            parent_run_id = tracking.start_run(
                experiment_name=req.experiment_name,
                run_name=req.validation_name,
                tags=build_parent_tags(
                    req=req,
                    report_out=report_out,
                    runs_csv_out=runs_csv_out,
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
                    "features_config_path": req.features_config_path,
                    "preset_name": req.preset_name,
                },
            )
            tracking.log_artifact(parent_run_id, snapshot_path, artifact_path="inputs")

        assert parent_run_id is not None

        existing_results = ()
        if parent_theme_state is not None:
            existing_results = parent_theme_state.effective_results
        baseline_metrics = resolve_baseline_metrics(existing_results, selected_scenarios)
        if baseline_metrics is None and selected_scenarios and selected_scenarios[0].scenario_name != "baseline_existing":
            raise ValueError("baseline_existing must be available before rerunning non-baseline scenarios.")

        attempt_counts = build_attempt_counts(parent_theme_state)
        run_validation_scenarios(
            req=req,
            deps=deps,
            parent_run_id=parent_run_id,
            selected_scenarios=selected_scenarios,
            original_text=original_text,
            run_log_dir=effective_run_log_dir,
            initial_baseline_metrics=baseline_metrics,
            attempt_counts=attempt_counts,
            tracker=scenario_tracker,
        )

        scenario_results = collect_effective_results(req=req, deps=deps, parent_run_id=parent_run_id)
        sync_effective_attempt_statuses(
            req=req,
            deps=deps,
            parent_run_id=parent_run_id,
            effective_results=scenario_results,
        )
        materialized_outputs = materialize_feature_validation_outputs(
            req=req,
            deps=deps,
            parent_run_id=parent_run_id,
            theme_revision=theme_revision,
            append_history=append_history,
            report_out=report_out,
            runs_csv_out=runs_csv_out,
            run_log_dir=effective_run_log_dir,
            scenario_results=scenario_results,
        )
        scenario_results = materialized_outputs.scenario_results
        theme_status = materialized_outputs.theme_status

        publish_feature_validation_parent_artifacts(
            deps=deps,
            parent_run_id=parent_run_id,
            report_out=report_out,
            runs_csv_out=runs_csv_out,
            run_log_dir=effective_run_log_dir,
            theme_revision=theme_revision,
            summary=materialized_outputs.summary,
        )
        tracking.log_tags(
            parent_run_id,
            {
                "decision": str(materialized_outputs.summary["decision"]),
                **build_parent_tags(
                    req=req,
                    report_out=report_out,
                    runs_csv_out=runs_csv_out,
                    theme_status=theme_status,
                    theme_revision=theme_revision,
                ),
            },
        )
        tracking.set_terminated(parent_run_id, status="FINISHED")

        return FeatureValidationResult(
            validation_name=req.validation_name,
            decision=str(materialized_outputs.summary["decision"]),
            theme_status=theme_status,
            theme_revision=theme_revision,
            report_path=report_out,
            runs_csv_path=runs_csv_out,
            run_log_dir=effective_run_log_dir,
            parent_run_id=parent_run_id,
            scenario_run_ids={result.scenario_name: result.scenario_run_id for result in scenario_results},
            effective_scenario_run_ids={result.scenario_name: result.scenario_run_id for result in scenario_results},
            new_scenario_run_ids=dict(scenario_tracker.new_scenario_run_ids),
            scenario_results=scenario_results,
            restored_features_state=restored_features_state,
        )
    except Exception:
        logger.exception(
            "feature validation scenario failed scenario=%s run_id=%s",
            scenario_tracker.current_scenario_name or "-",
            scenario_tracker.current_scenario_run_id or "-",
        )
        mark_started_scenario_runs_failed(tracking=tracking, tracker=scenario_tracker)
        if req.resume_parent_run_id is None:
            if parent_run_id is not None:
                try:
                    tracking.log_tags(parent_run_id, {"theme_status": "failed"})
                except Exception:
                    pass
            terminate_safely(tracking, parent_run_id, "FAILED")
        raise


def _load_original_features_text(
    *,
    req: FeatureValidationRequest,
    deps: FeatureValidationDeps,
) -> str:
    file_gateway = deps.file_gateway
    if not deps.feature_definition_port.is_registry_path(req.features_config_path):
        return file_gateway.read_text(req.features_config_path)

    baseline_scenario = next(
        (scenario for scenario in req.scenarios if scenario.scenario_name == "baseline_existing"),
        None,
    )
    if baseline_scenario is None or baseline_scenario.feature_set_diff is None:
        raise ValueError(
            "baseline_existing with feature_set is required when features_config_path points to registry."
        )

    feature_set = deps.feature_definition_port.load_feature_set(
        source_path=req.feature_sets_path,
        feature_set_name=baseline_scenario.feature_set_diff.base_feature_set_name,
        mode="production",
    )
    return deps.feature_definition_port.render_feature_config(
        feature_names=list(feature_set.feature_names),
        cat_features=list(feature_set.cat_features),
    )


def _validate_request(req: FeatureValidationRequest) -> None:
    if not req.validation_name.strip():
        raise ValueError("validation_name is required.")
    if not req.scenarios:
        raise ValueError("scenarios must not be empty.")
    scenario_names = [scenario.scenario_name for scenario in req.scenarios]
    if len(scenario_names) != len(set(scenario_names)):
        raise ValueError("scenario names must be unique.")
    if req.scenarios[0].scenario_name != "baseline_existing":
        raise ValueError("first scenario must be baseline_existing.")
    if req.final_selected_scenario and req.final_selected_scenario not in scenario_names:
        raise ValueError(f"unknown final_selected_scenario: {req.final_selected_scenario}")
    if req.final_selected_scenario and not req.finalize:
        raise ValueError("final_selected_scenario requires finalize.")


def _select_target_scenarios(req: FeatureValidationRequest) -> tuple[ValidationScenarioSpec, ...]:
    if req.resume_parent_run_id and req.finalize and not req.scenario_filter:
        return ()
    if not req.scenario_filter:
        return req.scenarios
    requested = set(req.scenario_filter)
    resolved = tuple(scenario for scenario in req.scenarios if scenario.scenario_name in requested)
    found = {scenario.scenario_name for scenario in resolved}
    missing = requested - found
    if missing:
        raise ValueError(f"scenario_filter contains unknown scenarios: {sorted(missing)}")
    return resolved
