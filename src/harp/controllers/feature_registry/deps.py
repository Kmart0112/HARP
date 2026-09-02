from __future__ import annotations

from harp.adapters.driven import LocalFileGatewayAdapter, YamlFeatureDefinitionAdapter
from harp.usecase.feature_registry import RenderFeatureSetDeps


def build_render_feature_set_deps() -> RenderFeatureSetDeps:
    file_gateway = LocalFileGatewayAdapter()
    return RenderFeatureSetDeps(
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
    )
