from __future__ import annotations

from harp.adapters.driven import MlflowTrackingAdapter
from harp.adapters.driven.db.race_input_repository import (
    SqlRaceInputRepository,
    mart_input_mapping,
)
from harp.adapters.driven.storage import (
    JsonManifestStoreAdapter,
    LocalFileGatewayAdapter,
    PickleArtifactStoreAdapter,
    YamlFeatureDefinitionAdapter,
)
from harp.config import HarpRuntimeConfig
from harp.shared.db import get_engine
from harp.usecase.training.dto import TrainDeps


def build_train_deps(config: HarpRuntimeConfig) -> TrainDeps:
    """Build driven adapter dependencies for the training usecase.

    Args:
        config: Runtime settings used for tracking and data source defaults.
    """

    file_gateway = LocalFileGatewayAdapter()
    return TrainDeps(
        training_repository=SqlRaceInputRepository(
            engine=get_engine(config.database.db_url),
            mapping=mart_input_mapping(config.mart.training_mart_table, quotes_table=config.mart.training_quotes_table,
                                       pre_start_minutes=10),
        ),
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
        artifact_store_port=PickleArtifactStoreAdapter(),
        manifest_store_port=JsonManifestStoreAdapter(),
        tracking_port=MlflowTrackingAdapter(tracking_uri=config.tracking.mlflow_tracking_uri),
        contract_path=config.paths.feature_sets_path,
    )
