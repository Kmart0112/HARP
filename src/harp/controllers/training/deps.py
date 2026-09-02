from __future__ import annotations

from harp.adapters.driven import MlflowTrackingAdapter
from harp.adapters.driven.db import PostgresPolarsTrainingRepositoryAdapter
from harp.adapters.driven.storage import (
    JsonManifestStoreAdapter,
    LocalFileGatewayAdapter,
    PickleArtifactStoreAdapter,
    YamlFeatureDefinitionAdapter,
)
from harp.config import HarpRuntimeConfig
from harp.usecase.training.dto import TrainDeps


def build_train_deps(config: HarpRuntimeConfig) -> TrainDeps:
    """Build driven adapter dependencies for the training usecase.

    Args:
        config: Runtime settings used for tracking and data source defaults.
    """

    file_gateway = LocalFileGatewayAdapter()
    return TrainDeps(
        training_repository=PostgresPolarsTrainingRepositoryAdapter(
            db_url=config.database.db_url,
        ),
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
        artifact_store_port=PickleArtifactStoreAdapter(),
        manifest_store_port=JsonManifestStoreAdapter(),
        tracking_port=MlflowTrackingAdapter(tracking_uri=config.tracking.mlflow_tracking_uri),
        mart_table=config.mart.training_mart_table,
        contract_path=config.paths.feature_sets_path,
        source_table=config.mart.training_mart_table,
    )
