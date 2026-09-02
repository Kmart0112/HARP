from __future__ import annotations

from harp.adapters.driven import LocalFileGatewayAdapter, YamlFeatureDefinitionAdapter
from harp.usecase import ExportFeatureContractDeps


def build_export_feature_contract_deps() -> ExportFeatureContractDeps:
    file_gateway = LocalFileGatewayAdapter()
    return ExportFeatureContractDeps(
        file_gateway=file_gateway,
        feature_definition_port=YamlFeatureDefinitionAdapter(file_gateway),
    )
