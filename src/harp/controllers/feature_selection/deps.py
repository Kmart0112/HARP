from __future__ import annotations

from harp.adapters.driven import (
    LocalFileGatewayAdapter,
    MlflowTrackingAdapter,
    TrackingParentArtifactPublisherAdapter,
    YamlFeatureDefinitionAdapter,
)
from harp.adapters.driven.validation import MarimoFeatureValidationMetricsRunnerAdapter
from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root
from harp.usecase import FeatureSelectionDeps


def build_feature_selection_deps(config: HarpRuntimeConfig) -> FeatureSelectionDeps:
    root = str(project_root())
    file_gateway = LocalFileGatewayAdapter()
    tracking_port = MlflowTrackingAdapter(
        tracking_uri=config.tracking.mlflow_tracking_uri,
    )
    return FeatureSelectionDeps(
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
        tracking_port=tracking_port,
        parent_artifact_publisher=TrackingParentArtifactPublisherAdapter(
            file_gateway=file_gateway,
            tracking=tracking_port,
        ),
        metrics_runner_port=MarimoFeatureValidationMetricsRunnerAdapter(project_root=root),
    )
