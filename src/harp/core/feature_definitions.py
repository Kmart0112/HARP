from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureSetDefinition:
    feature_names: tuple[str, ...]
    cat_features: tuple[str, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.feature_names:
            raise ValueError("feature_names must not be empty.")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must not contain duplicates.")
        missing = [feature for feature in self.cat_features if feature not in self.feature_names]
        if missing:
            raise ValueError(f"cat features are missing from feature_names: {missing}")


def is_feature_registry_document(document: object) -> bool:
    return isinstance(document, dict) and isinstance(document.get("features"), list)


def resolve_registry_feature_set(
    document: object,
    *,
    feature_set_name: str,
    mode: str,
    source: str,
) -> FeatureSetDefinition:
    if not is_feature_registry_document(document):
        raise ValueError(f"feature registry must define features: {source}")

    registry = document
    assert isinstance(registry, dict)
    include_statuses = _resolve_include_statuses(registry, mode=mode)
    requested_name = str(feature_set_name).strip()
    resolved_items: list[tuple[int, int, str, str]] = []
    found_any_mapping = False

    for index, item in enumerate(registry["features"]):
        if not isinstance(item, dict):
            raise ValueError(f"feature entry must be mapping: {source}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"feature name is invalid: {source}")
        role = item.get("role")
        if not isinstance(role, str) or not role.strip():
            raise ValueError(f"feature role is invalid: {name}")

        set_status = item.get("set_status", {})
        if not isinstance(set_status, dict):
            raise ValueError(f"set_status must be mapping: {name}")
        raw_status = set_status.get(requested_name)
        if raw_status is None:
            continue
        found_any_mapping = True
        normalized_status, order = _normalize_set_status(raw_status)
        if normalized_status in include_statuses:
            resolved_items.append((order, index, name, role))

    if not found_any_mapping:
        raise KeyError(f"feature set not found in registry: {requested_name}")
    if not resolved_items:
        raise ValueError(f"resolved feature_names is empty for set: {requested_name}.{mode}")

    resolved_items.sort(key=lambda item: (item[0], item[1], item[2]))
    feature_names = tuple(name for _order, _index, name, _role in resolved_items)
    cat_features = tuple(
        name
        for _order, _index, name, role in resolved_items
        if role == "categorical_feature"
    )
    return FeatureSetDefinition(
        name=requested_name,
        feature_names=feature_names,
        cat_features=cat_features,
    )


def parse_feature_config_document(document: object, *, source: str) -> FeatureSetDefinition:
    if not isinstance(document, dict):
        raise ValueError(f"feature config must be a mapping: {source}")
    cat_features = document.get("cat_features")
    if cat_features is None:
        cat_features = []
    return _build_feature_set_definition(
        name=None,
        feature_names=document.get("feature_names"),
        cat_features=cat_features,
        source=source,
    )


def parse_feature_contract_document(document: object, *, source: str) -> FeatureSetDefinition:
    if not isinstance(document, dict):
        raise ValueError(f"feature set contract must be mapping: {source}")
    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"name is invalid in file: {source}")
    return _build_feature_set_definition(
        name=name.strip(),
        feature_names=document.get("feature_names"),
        cat_features=document.get("cat_features"),
        source=source,
    )


def _build_feature_set_definition(
    *,
    name: str | None,
    feature_names: object,
    cat_features: object,
    source: str,
) -> FeatureSetDefinition:
    if not isinstance(feature_names, list) or not feature_names:
        raise ValueError(f"feature_names is invalid: {source}")
    if not all(isinstance(item, str) and item.strip() for item in feature_names):
        raise ValueError(f"feature_names must contain non-empty strings: {source}")
    if not isinstance(cat_features, list):
        raise ValueError(f"cat_features is invalid: {source}")
    if not all(isinstance(item, str) and item.strip() for item in cat_features):
        raise ValueError(f"cat_features must contain non-empty strings: {source}")
    return FeatureSetDefinition(
        name=name,
        feature_names=tuple(item.strip() for item in feature_names),
        cat_features=tuple(item.strip() for item in cat_features),
    )


def _resolve_include_statuses(document: dict[str, Any], *, mode: str) -> set[str]:
    selection_rules = document.get("selection_rules", {})
    if not isinstance(selection_rules, dict):
        raise ValueError("selection_rules must be mapping")
    selected_rule = selection_rules.get(mode)
    if selected_rule is None and mode != "production":
        selected_rule = selection_rules.get("production")
    if not isinstance(selected_rule, dict):
        raise ValueError(f"selection rule is invalid: {mode}")
    include_statuses = selected_rule.get("include_statuses")
    if not isinstance(include_statuses, list) or not include_statuses:
        raise ValueError(f"include_statuses is invalid: {mode}")
    return {_normalize_status(item) for item in include_statuses}


def _normalize_status(value: object) -> str:
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value).strip()


def _normalize_set_status(value: object) -> tuple[str, int]:
    if isinstance(value, dict):
        status = _normalize_status(value.get("status"))
        raw_order = value.get("order")
        if not isinstance(raw_order, int) or raw_order <= 0:
            raise ValueError(f"set_status.order must be positive integer: {value}")
        return status, raw_order
    return _normalize_status(value), 1_000_000
