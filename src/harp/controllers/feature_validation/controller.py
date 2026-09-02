from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root
from harp.usecase import (
    FeatureDefinitionSpec,
    FeatureSetDiffSpec,
    FeatureToggleSpec,
    FeatureValidationReportSpec,
    FeatureValidationRequest,
    ShapReviewSpec,
    ValidationScenarioSpec,
    run_feature_validation_usecase,
)

from .deps import build_feature_validation_deps as _build_feature_validation_deps
from .preset_loader import FeatureValidationPresetModel, load_feature_validation_preset


@dataclass(frozen=True)
class FeatureValidationCommand:
    """Command values for a feature validation workflow run.

    Args:
        preset: Preset file name to load from the feature validation preset directory.
        preset_name: Stable preset label recorded in reports and tracking.
        report_out: Optional report output path. Preset defaults are used when omitted.
        runs_csv_out: Optional validation runs CSV output path.
        run_log_dir: Optional directory for per-run logs.
        command: Optional command string recorded in the report.
        git_commit: Optional git commit recorded in the report.
        resume_parent_run_id: Optional parent run id to append to.
        only_scenarios: Scenario names to run when filtering the preset.
        finalize: Whether to mark the validation as final.
        final_selected_scenario: Optional scenario chosen during finalization.
        append_note: Optional note appended to the report.
    """

    preset: str
    preset_name: str
    report_out: str | None = None
    runs_csv_out: str | None = None
    run_log_dir: str | None = None
    command: str | None = None
    git_commit: str | None = None
    resume_parent_run_id: str | None = None
    only_scenarios: tuple[str, ...] = ()
    finalize: bool = False
    final_selected_scenario: str | None = None
    append_note: str | None = None


class FeatureValidationController:
    """Build feature validation usecase input from a preset command."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: FeatureValidationCommand):
        """Run the feature validation workflow.

        Args:
            cmd: CLI-level command values for feature validation.
        """

        req = _build_feature_validation_request(cmd, self._config)
        deps = _build_feature_validation_deps(self._config)
        return run_feature_validation_usecase(req, deps)


def _build_feature_validation_request(
    cmd: FeatureValidationCommand,
    config: HarpRuntimeConfig,
) -> FeatureValidationRequest:
    preset = load_feature_validation_preset(str(cmd.preset).strip())
    root = project_root()
    today_token = datetime.now().strftime("%Y%m%d")

    report_out = cmd.report_out or str(
        root / "notebook" / "report" / "features" / preset.outputs.report_file.format(date=today_token)
    )
    runs_csv_out = cmd.runs_csv_out or str(
        root / "notebook" / "report" / "results" / preset.outputs.runs_csv_file.format(date=today_token)
    )
    run_log_dir = cmd.run_log_dir or str(root / "outputs" / preset.outputs.run_log_dir.format(date=today_token))

    return FeatureValidationRequest(
        validation_name=preset.validation.name,
        category=preset.validation.category,
        change_summary=preset.validation.change_summary,
        experiment_name=preset.validation.experiment_name or config.tracking.feature_validation_experiment,
        preset_name=cmd.preset_name,
        features_config_path=str(root / config.paths.feature_sets_path),
        feature_sets_path=str(root / "contracts" / "features"),
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        run_log_dir=run_log_dir,
        command=cmd.command or f"uv run python -m pipeline.jobs.run_feature_validation --preset {cmd.preset}",
        git_commit=cmd.git_commit or "unknown",
        resume_parent_run_id=cmd.resume_parent_run_id,
        scenario_filter=cmd.only_scenarios,
        finalize=cmd.finalize,
        final_selected_scenario=cmd.final_selected_scenario,
        append_note=cmd.append_note,
        scenarios=_build_scenarios(preset),
        report_spec=_build_report_spec(preset),
    )


def _build_scenarios(preset: FeatureValidationPresetModel) -> tuple[ValidationScenarioSpec, ...]:
    scenarios: list[ValidationScenarioSpec] = []
    for scenario in preset.scenarios:
        shap_request = None
        if scenario.shap is not None:
            shap_request = ShapReviewSpec(
                candidate_feature=scenario.shap.candidate_feature,
                comparison_features=tuple(scenario.shap.comparison_features),
                validation_mode=scenario.validation_mode,
                report_run_label=scenario.shap.report_run_label,
            )
        scenarios.append(
            ValidationScenarioSpec(
                scenario_name=scenario.scenario_name,
                toggles=tuple(
                    FeatureToggleSpec(
                        feature_name=toggle.feature_name,
                        sections=tuple(toggle.sections),
                        enabled=toggle.enabled,
                    )
                    for toggle in scenario.toggles
                ),
                validation_mode=scenario.validation_mode,
                feature_set_diff=(
                    None
                    if scenario.feature_set is None
                    else FeatureSetDiffSpec(
                        base_feature_set_name=scenario.feature_set.base_feature_set_name,
                        include_features=tuple(scenario.feature_set.include_features),
                        exclude_features=tuple(scenario.feature_set.exclude_features),
                        include_cat_features=tuple(scenario.feature_set.include_cat_features),
                        exclude_cat_features=tuple(scenario.feature_set.exclude_cat_features),
                    )
                ),
                shap_request=shap_request,
            )
        )
    return tuple(scenarios)


def _build_report_spec(preset: FeatureValidationPresetModel) -> FeatureValidationReportSpec:
    return FeatureValidationReportSpec(
        title=preset.report.title,
        background=preset.report.background,
        hypothesis_lines=tuple(preset.report.hypothesis_lines),
        target_features=tuple(
            FeatureDefinitionSpec(
                feature_name=feature.feature_name,
                feature_type=feature.feature_type,
                change_type=feature.change_type,
                summary=feature.summary,
                sections=tuple(feature.sections),
                comparison_features=tuple(feature.comparison_features),
                dbt_model_path=feature.dbt_model_path,
                dbt_yaml_path=feature.dbt_yaml_path,
                final_column=feature.final_column,
            )
            for feature in preset.target_features
        ),
        leakage_notes=tuple(preset.report.leakage_notes),
        implementation_notes=tuple(preset.report.implementation_notes),
        metrics_notebook_path=preset.report.metrics_notebook_path,
        shap_notebook_path=preset.report.shap_notebook_path,
    )

__all__ = [
    "FeatureValidationController",
    "FeatureValidationCommand",
    "_build_feature_validation_deps",
    "_build_feature_validation_request",
    "_build_report_spec",
    "_build_scenarios",
]
