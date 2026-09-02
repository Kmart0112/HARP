from __future__ import annotations

from dataclasses import dataclass

from harp.adapters.driven import LocalFileGatewayAdapter, YamlFeatureDefinitionAdapter
from harp.interface.ports import FeatureDefinitionPort, FileGatewayPort


@dataclass(frozen=True)
class NotebookFeatureConfigDeps:
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort


def build_notebook_feature_config_deps() -> NotebookFeatureConfigDeps:
    file_gateway = LocalFileGatewayAdapter()
    return NotebookFeatureConfigDeps(
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
    )
