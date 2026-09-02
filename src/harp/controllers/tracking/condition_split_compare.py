from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harp.config import HarpRuntimeConfig
from harp.usecase import (
    ConditionSplitCompareTrackingRequest,
    run_log_condition_split_compare_usecase,
)

from .deps import (
    build_condition_split_compare_tracking_deps as _build_condition_split_compare_tracking_deps,
)


@dataclass(frozen=True)
class ConditionSplitCompareTrackingCommand:
    """Command values for logging condition split compare artifacts.

    Args:
        summary_csv_path: Path to the summary CSV produced by the compare job.
        slices_csv_path: Path to the per-slice CSV produced by the compare job.
        experiment_name: MLflow experiment name used for the tracking run.
        run_name: Optional MLflow run name. Defaults to the summary file stem.
        parent_run_id: Optional parent run id for nested tracking.
        tags: Optional MLflow tags attached to the run.
    """

    summary_csv_path: str
    slices_csv_path: str
    experiment_name: str = "condition_split_compare"
    run_name: str | None = None
    parent_run_id: str | None = None
    tags: dict[str, str] | None = None


class ConditionSplitCompareTrackingController:
    """Build tracking usecase input from a command and app settings."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: ConditionSplitCompareTrackingCommand):
        """Log condition split compare files through the tracking usecase.

        Args:
            cmd: CLI-level command values for the compare tracking run.
        """

        req = _build_condition_split_compare_tracking_request(cmd)
        deps = _build_condition_split_compare_tracking_deps(self._config)
        return run_log_condition_split_compare_usecase(req, deps)


def _build_condition_split_compare_tracking_request(
    cmd: ConditionSplitCompareTrackingCommand,
) -> ConditionSplitCompareTrackingRequest:
    summary_csv_path = str(Path(cmd.summary_csv_path).resolve())
    slices_csv_path = str(Path(cmd.slices_csv_path).resolve())
    run_name = cmd.run_name or Path(summary_csv_path).stem
    return ConditionSplitCompareTrackingRequest(
        experiment_name=cmd.experiment_name,
        run_name=run_name,
        summary_csv_path=summary_csv_path,
        slices_csv_path=slices_csv_path,
        parent_run_id=cmd.parent_run_id,
        tags=dict(cmd.tags or {}),
    )


__all__ = [
    "ConditionSplitCompareTrackingController",
    "ConditionSplitCompareTrackingCommand",
    "_build_condition_split_compare_tracking_deps",
    "_build_condition_split_compare_tracking_request",
]
