from __future__ import annotations

from harp.adapters.driven import LocalFileGatewayAdapter, LocalMlflowStoreAdapter
from harp.usecase.mlflow_store.dto import MlflowStoreMigrationDeps


def build_mlflow_store_migration_deps() -> MlflowStoreMigrationDeps:
    return MlflowStoreMigrationDeps(
        file_gateway=LocalFileGatewayAdapter(),
        mlflow_store_port=LocalMlflowStoreAdapter(),
    )
