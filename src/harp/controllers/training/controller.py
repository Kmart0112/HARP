from __future__ import annotations

from dataclasses import replace

from harp.config import HarpRuntimeConfig
from harp.usecase.training.dto import CalibrationMethod, TrainPipelineKind
from harp.usecase.training.usecase import run_train_pipeline_usecase

from .command import TrainCommand, build_train_request, resolve_training_where as _resolve_training_where
from .deps import build_train_deps as _build_train_deps


class TrainController:
    """Build training usecase input from a training command and settings."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: TrainCommand):
        """Run the configured training pipeline.

        Args:
            cmd: CLI-level command values for training.
        """

        req = build_train_request(cmd)
        req = replace(
            req,
            tracking_experiment_name=self._config.tracking.train_experiment,
            tracking_run_name=f"train_{req.pipeline_kind.value}_{req.calibration_method.value}",
        )

        deps = _build_train_deps(self._config)
        return run_train_pipeline_usecase(req, deps)


__all__ = [
    "CalibrationMethod",
    "TrainController",
    "TrainCommand",
    "TrainPipelineKind",
    "_build_train_deps",
    "_resolve_training_where",
]
