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


def build_nn_train_deps(input_root: str, prepared_root: str, model_root: str, *, tracking_uri: str | None = None):
    # Optional torch dependency is imported only when entering an NN operation.
    from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
    from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
    from harp.adapters.driven.storage.nn_model_store import TorchNnModelStore
    from harp.usecase.training.nn_dto import NnTrainDeps

    return NnTrainDeps(ParquetNnDatasetStore(input_root), JsonNnPreparedDatasetStore(prepared_root),
                       TorchNnModelStore(model_root),
                       MlflowTrackingAdapter(tracking_uri=tracking_uri) if tracking_uri else None)


def build_nn_recipe_reader():
    from harp.adapters.driven.storage.nn_training_recipe import YamlNnTrainingRecipeReader
    return YamlNnTrainingRecipeReader()


def resolve_nn_device(requested: str) -> str:
    import torch
    from harp.core.nn.contracts import NnInputContractError

    available = {"cpu": True, "cuda": torch.cuda.is_available(), "mps": torch.backends.mps.is_available()}
    if requested == "auto":
        return next(name for name in ("cuda", "mps", "cpu") if available[name])
    if requested not in available or not available[requested]:
        raise NnInputContractError(f"requested NN device is unavailable: {requested}")
    return requested
