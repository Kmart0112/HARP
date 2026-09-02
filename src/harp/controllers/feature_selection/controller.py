from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root
from harp.usecase import (
    AggregateGroupSpec,
    FeatureSelectionReportSpec,
    FeatureSelectionRequest,
    VariantGroupSpec,
    run_feature_selection_usecase,
)

from .deps import build_feature_selection_deps as _build_feature_selection_deps
from .preset_loader import load_feature_selection_preset


@dataclass(frozen=True)
class FeatureSelectionCommand:
    """Command values for a feature selection workflow run.

    Args:
        preset: Preset file name to load from the feature selection preset directory.
        preset_name: Stable preset label recorded in reports and tracking.
        report_out: Optional report output path. Preset defaults are used when omitted.
        runs_csv_out: Optional validation runs CSV output path.
        decisions_csv_out: Optional selection decisions CSV output path.
        selected_contract_snapshot_out: Optional selected contract snapshot output path.
        run_log_dir: Optional directory for per-run logs.
        command: Optional command string recorded in the report.
        git_commit: Optional git commit recorded in the report.
        resume_parent_run_id: Optional parent run id to append to.
        only_scenarios: Scenario names to run when filtering the preset.
        finalize: Whether to mark the selection as final.
        append_note: Optional note appended to the report.
        write_contract: Whether to write the selected contract.
    """

    preset: str
    preset_name: str
    report_out: str | None = None
    runs_csv_out: str | None = None
    decisions_csv_out: str | None = None
    selected_contract_snapshot_out: str | None = None
    run_log_dir: str | None = None
    command: str | None = None
    git_commit: str | None = None
    resume_parent_run_id: str | None = None
    only_scenarios: tuple[str, ...] = ()
    finalize: bool = False
    append_note: str | None = None
    write_contract: bool = False


class FeatureSelectionController:
    """Build feature selection usecase input from a preset command."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: FeatureSelectionCommand):
        """Run the feature selection workflow.

        Args:
            cmd: CLI-level command values for feature selection.
        """

        req = _build_feature_selection_request(cmd, self._config)
        deps = _build_feature_selection_deps(self._config)
        return run_feature_selection_usecase(req, deps)


def _build_feature_selection_request(
    cmd: FeatureSelectionCommand,
    config: HarpRuntimeConfig,
) -> FeatureSelectionRequest:
    preset = load_feature_selection_preset(str(cmd.preset).strip())
    root = project_root()
    today_token = datetime.now().strftime("%Y%m%d")

    report_out = cmd.report_out or str(
        root / "notebook" / "report" / "features" / preset.outputs.report_file.format(date=today_token)
    )
    runs_csv_out = cmd.runs_csv_out or str(
        root / "notebook" / "report" / "results" / preset.outputs.runs_csv_file.format(date=today_token)
    )
    decisions_csv_out = cmd.decisions_csv_out or str(
        root / "notebook" / "report" / "results" / preset.outputs.decisions_csv_file.format(date=today_token)
    )
    selected_contract_snapshot_out = cmd.selected_contract_snapshot_out or str(
        root / "outputs" / preset.outputs.selected_contract_file.format(date=today_token)
    )
    run_log_dir = cmd.run_log_dir or str(root / "outputs" / preset.outputs.run_log_dir.format(date=today_token))

    return FeatureSelectionRequest(
        validation_name=preset.validation.name,
        category=preset.validation.category,
        change_summary=preset.validation.change_summary,
        experiment_name=preset.validation.experiment_name or config.tracking.feature_selection_experiment,
        preset_name=cmd.preset_name,
        feature_sets_path=str(root / config.paths.feature_sets_path),
        target_contract_path=str(root / preset.selection.target_contract_path),
        report_out=report_out,
        runs_csv_out=runs_csv_out,
        decisions_csv_out=decisions_csv_out,
        selected_contract_snapshot_out=selected_contract_snapshot_out,
        run_log_dir=run_log_dir,
        command=cmd.command or f"uv run python -m pipeline.jobs.run_feature_selection --preset {cmd.preset}",
        git_commit=cmd.git_commit or "unknown",
        resume_parent_run_id=cmd.resume_parent_run_id,
        scenario_filter=cmd.only_scenarios,
        finalize=cmd.finalize,
        append_note=cmd.append_note,
        write_contract=cmd.write_contract,
        base_feature_set_name=preset.selection.base_feature_set_name,
        aggregate_groups=tuple(
            AggregateGroupSpec(
                group_id=group.group_id,
                aggregate_features=tuple(group.aggregate_features),
                source_features=tuple(group.source_features),
            )
            for group in preset.selection.aggregate_groups
        ),
        variant_groups=tuple(
            VariantGroupSpec(
                group_id=group.group_id,
                candidates=tuple(group.candidates),
            )
            for group in preset.selection.variant_groups
        ),
        report_spec=FeatureSelectionReportSpec(
            title=preset.report.title,
            background=preset.report.background,
            hypothesis_lines=tuple(preset.report.hypothesis_lines),
            leakage_notes=tuple(preset.report.leakage_notes),
            implementation_notes=tuple(preset.report.implementation_notes),
        ),
    )

__all__ = [
    "FeatureSelectionController",
    "FeatureSelectionCommand",
    "_build_feature_selection_deps",
    "_build_feature_selection_request",
]
