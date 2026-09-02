from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import FileGatewayPort, MlflowStorePort


@dataclass(frozen=True)
class MlflowStoreMigrationRequest:
    source_store_dir: str
    target_tracking_uri: str
    check_only: bool


@dataclass(frozen=True)
class MlflowStoreMigrationDeps:
    file_gateway: FileGatewayPort
    mlflow_store_port: MlflowStorePort


@dataclass(frozen=True)
class MlflowStoreMigrationResult:
    source_store_dir: str
    target_store_dir: str
    target_tracking_uri: str
    check_only: bool
    copied_files: tuple[str, ...]
    rewritten_meta_files: tuple[str, ...]
    verified_experiment_names: tuple[str, ...]
