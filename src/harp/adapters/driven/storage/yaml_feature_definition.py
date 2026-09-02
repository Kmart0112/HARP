from __future__ import annotations

import yaml

from harp.core.feature_definitions import (
    FeatureSetDefinition,
    is_feature_registry_document,
    parse_feature_config_document,
    parse_feature_contract_document,
    resolve_registry_feature_set,
)
from harp.interface.ports import FileGatewayPort


class YamlFeatureDefinitionAdapter:
    def __init__(self, file_gateway: FileGatewayPort) -> None:
        self._file_gateway = file_gateway

    def is_registry_path(self, path: str) -> bool:
        if not str(path).lower().endswith((".yaml", ".yml")):
            return False
        if not self._file_gateway.exists(path):
            return False
        try:
            document = yaml.safe_load(self._file_gateway.read_text(path))
        except (FileNotFoundError, KeyError, yaml.YAMLError):
            return False
        return is_feature_registry_document(document)

    def load_feature_set(
        self,
        *,
        source_path: str,
        feature_set_name: str,
        mode: str = "production",
    ) -> FeatureSetDefinition:
        if self.is_registry_path(source_path):
            document = self._load_yaml(source_path)
            return resolve_registry_feature_set(
                document,
                feature_set_name=feature_set_name,
                mode=mode,
                source=source_path,
            )

        contract_files = sorted(
            path
            for path in self._file_gateway.list_files(source_path)
            if path.lower().endswith((".yaml", ".yml"))
        )
        if not contract_files:
            raise ValueError(f"no feature set files found in contract directory: {source_path}")

        contracts: dict[str, FeatureSetDefinition] = {}
        for file_path in contract_files:
            contract = parse_feature_contract_document(self._load_yaml(file_path), source=file_path)
            assert contract.name is not None
            if contract.name in contracts:
                raise ValueError(f"duplicate feature set name in contract directory: {contract.name}")
            contracts[contract.name] = contract
        try:
            return contracts[feature_set_name]
        except KeyError as exc:
            raise KeyError(f"feature set not found in contract directory: {feature_set_name}") from exc

    def parse_feature_config_text(self, text: str, *, source: str) -> FeatureSetDefinition:
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid feature config YAML: {source}") from exc
        return parse_feature_config_document(document, source=source)

    def render_feature_config(
        self,
        *,
        feature_names: list[str],
        cat_features: list[str],
    ) -> str:
        parse_feature_config_document(
            {"feature_names": list(feature_names), "cat_features": list(cat_features)},
            source="generated feature config",
        )
        return yaml.safe_dump(
            {"feature_names": list(feature_names), "cat_features": list(cat_features)},
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    def parse_contract_text(self, text: str, *, source: str) -> FeatureSetDefinition | None:
        try:
            document = yaml.safe_load(text)
            return parse_feature_contract_document(document, source=source)
        except (ValueError, yaml.YAMLError):
            return None

    def render_contract(
        self,
        *,
        contract_name: str,
        feature_names: list[str],
        cat_features: list[str],
    ) -> str:
        payload = {
            "name": contract_name,
            "feature_names": list(feature_names),
            "cat_features": list(cat_features),
        }
        parse_feature_contract_document(payload, source="generated feature contract")
        return yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    def find_contract_path(self, *, contract_dir: str, feature_set_name: str) -> str:
        for file_path in sorted(self._file_gateway.list_files(contract_dir)):
            if not file_path.lower().endswith((".yaml", ".yml")):
                continue
            try:
                contract = parse_feature_contract_document(self._load_yaml(file_path), source=file_path)
            except ValueError:
                continue
            if contract.name == feature_set_name:
                return file_path
        raise KeyError(f"feature set not found in contract directory: {feature_set_name}")

    def _load_yaml(self, path: str) -> object:
        try:
            return yaml.safe_load(self._file_gateway.read_text(path))
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML: {path}") from exc
