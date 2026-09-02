from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import FeatureDefinitionPort, FileGatewayPort


@dataclass(frozen=True)
class ExportFeatureContractRequest:
    registry_path: str
    feature_set_name: str
    target_path: str
    contract_name: str | None
    dry_run: bool
    emit_stdout: bool
    allow_create: bool
    check_only: bool
    validate_name_match: bool
    quiet: bool


@dataclass(frozen=True)
class ExportFeatureContractDeps:
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort


@dataclass(frozen=True)
class ExportFeatureContractResult:
    target_path: str
    contract_name: str
    feature_names: list[str]
    cat_features: list[str]
    changed: bool
    created: bool
    check_only: bool
    yaml_text: str
    added_features: list[str]
    removed_features: list[str]
