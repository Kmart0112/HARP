from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root
from harp.usecase.mlflow_store.dto import MlflowStoreMigrationRequest
from harp.usecase.mlflow_store.migration import run_migrate_mlflow_store_usecase

from .deps import (
    build_mlflow_store_migration_deps as _build_mlflow_store_migration_deps,
)


@dataclass(frozen=True)
class MlflowStoreMigrationCommand:
    """Command values for migrating the local MLflow file store.

    Args:
        source_store_dir: Optional source MLflow file-store directory.
        target_tracking_uri: Optional target tracking URI. Settings are used when omitted.
        check: Report the migration plan without writing.
    """

    source_store_dir: str | None = None
    target_tracking_uri: str | None = None
    check: bool = False


class MlflowStoreMigrationController:
    """Build MLflow store migration usecase input from a command."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: MlflowStoreMigrationCommand):
        """Run the MLflow store migration flow.

        Args:
            cmd: CLI-level command values for the migration.
        """

        req = _build_mlflow_store_migration_request(cmd, self._config)
        deps = _build_mlflow_store_migration_deps()
        return run_migrate_mlflow_store_usecase(req, deps)


def _build_mlflow_store_migration_request(
    cmd: MlflowStoreMigrationCommand,
    config: HarpRuntimeConfig,
) -> MlflowStoreMigrationRequest:
    root = project_root()
    source_store_dir = cmd.source_store_dir or str(root / "notebook" / "tmp" / "mlflow")
    return MlflowStoreMigrationRequest(
        source_store_dir=str(Path(source_store_dir).resolve()),
        target_tracking_uri=cmd.target_tracking_uri or config.tracking.mlflow_tracking_uri,
        check_only=cmd.check,
    )


__all__ = [
    "MlflowStoreMigrationController",
    "MlflowStoreMigrationCommand",
    "_build_mlflow_store_migration_deps",
    "_build_mlflow_store_migration_request",
]
