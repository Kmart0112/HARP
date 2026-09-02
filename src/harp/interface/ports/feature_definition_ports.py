from __future__ import annotations

from typing import Protocol

from harp.core.feature_definitions import FeatureSetDefinition


class FeatureDefinitionPort(Protocol):
    def is_registry_path(self, path: str) -> bool:
        ...

    def load_feature_set(
        self,
        *,
        source_path: str,
        feature_set_name: str,
        mode: str = "production",
    ) -> FeatureSetDefinition:
        ...

    def parse_feature_config_text(self, text: str, *, source: str) -> FeatureSetDefinition:
        ...

    def render_feature_config(
        self,
        *,
        feature_names: list[str],
        cat_features: list[str],
    ) -> str:
        ...

    def parse_contract_text(self, text: str, *, source: str) -> FeatureSetDefinition | None:
        ...

    def render_contract(
        self,
        *,
        contract_name: str,
        feature_names: list[str],
        cat_features: list[str],
    ) -> str:
        ...

    def find_contract_path(self, *, contract_dir: str, feature_set_name: str) -> str:
        ...
