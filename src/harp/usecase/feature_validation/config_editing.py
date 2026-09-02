from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from harp.interface.ports import FeatureDefinitionPort

from ..theme_tracking import safe_token
from .dto import FeatureSetDiffSpec, ValidationScenarioSpec

_SECTION_PATTERN = re.compile(r"^[A-Za-z0-9_]+:\s*$")


@dataclass(frozen=True)
class ResolvedScenarioConfig:
    feature_names: tuple[str, ...]
    cat_features: tuple[str, ...]
    scenario_text: str


def write_original_snapshot(*, run_log_dir: str, file_gateway, original_text: str) -> str:  # noqa: ANN001
    snapshot_path = str(Path(run_log_dir) / "inputs" / "features_original.yml")
    file_gateway.write_text(snapshot_path, original_text)
    return snapshot_path


def write_scenario_features_config(
    *,
    run_log_dir: str,
    file_gateway,  # noqa: ANN001
    scenario_name: str,
    scenario_text: str,
) -> str:
    scenario_path = str(Path(run_log_dir) / "inputs" / f"features_{safe_token(scenario_name)}.yml")
    file_gateway.write_text(scenario_path, scenario_text)
    return scenario_path


def resolve_scenario_config(
    *,
    original_text: str,
    scenario: ValidationScenarioSpec,
    feature_definition_port: FeatureDefinitionPort,
    feature_sets_path: str,
) -> ResolvedScenarioConfig:
    if scenario.feature_set_diff is None:
        scenario_text = apply_feature_toggles(original_text, scenario)
    else:
        feature_names, cat_features = resolve_feature_set_diff(
            feature_definition_port=feature_definition_port,
            feature_sets_path=feature_sets_path,
            diff=scenario.feature_set_diff,
        )
        scenario_text = feature_definition_port.render_feature_config(
            feature_names=feature_names,
            cat_features=cat_features,
        )
    return build_resolved_scenario_config(
        scenario_text,
        feature_definition_port=feature_definition_port,
    )


def ensure_required_feature_lines_present(text: str, scenarios: tuple[ValidationScenarioSpec, ...]) -> None:
    for scenario in scenarios:
        if scenario.feature_set_diff is not None:
            continue
        for toggle in scenario.toggles:
            for section in toggle.sections:
                find_feature_line_index(text, section=section, feature=toggle.feature_name)


def apply_feature_toggles(text: str, scenario: ValidationScenarioSpec) -> str:
    next_text = text
    for toggle in scenario.toggles:
        for section in toggle.sections:
            next_text = set_feature_state_in_section(
                next_text,
                section=section,
                feature=toggle.feature_name,
                enabled=toggle.enabled,
            )
    return next_text


def resolve_feature_set_diff(
    *,
    feature_definition_port: FeatureDefinitionPort,
    feature_sets_path: str,
    diff: FeatureSetDiffSpec,
) -> tuple[list[str], list[str]]:
    feature_set = feature_definition_port.load_feature_set(
        source_path=feature_sets_path,
        feature_set_name=diff.base_feature_set_name,
        mode="production",
    )
    feature_names = list(feature_set.feature_names)
    cat_features = list(feature_set.cat_features)
    feature_names = merge_feature_list(feature_names, diff.include_features, diff.exclude_features)
    cat_features = merge_feature_list(cat_features, diff.include_cat_features, diff.exclude_cat_features)

    feature_name_set = set(feature_names)
    cat_features = [feature for feature in cat_features if feature in feature_name_set]
    for feature in diff.include_cat_features:
        if feature not in feature_name_set:
            raise ValueError(f"cat feature not present in resolved feature_names: {feature}")
    return feature_names, cat_features


def merge_feature_list(base: list[str], includes: tuple[str, ...], excludes: tuple[str, ...]) -> list[str]:
    merged = [feature for feature in base if feature not in set(excludes)]
    seen = set(merged)
    for feature in includes:
        if feature in seen:
            continue
        merged.append(feature)
        seen.add(feature)
    return merged


def build_resolved_scenario_config(
    scenario_text: str,
    *,
    feature_definition_port: FeatureDefinitionPort,
) -> ResolvedScenarioConfig:
    feature_set = feature_definition_port.parse_feature_config_text(
        scenario_text,
        source="scenario features config",
    )
    return ResolvedScenarioConfig(
        feature_names=feature_set.feature_names,
        cat_features=feature_set.cat_features,
        scenario_text=scenario_text,
    )


def find_feature_line_index(text: str, *, section: str, feature: str) -> int:
    lines = text.splitlines()
    section_line = f"{section}:"
    try:
        section_start = next(i for i, line in enumerate(lines) if line.strip() == section_line)
    except StopIteration as exc:
        raise ValueError(f"section not found: {section}") from exc

    section_end = len(lines)
    for idx in range(section_start + 1, len(lines)):
        if _SECTION_PATTERN.match(lines[idx].strip()):
            section_end = idx
            break

    matches = [
        idx
        for idx in range(section_start + 1, section_end)
        if match_feature_line(feature, lines[idx]) is not None
    ]
    if len(matches) != 1:
        raise ValueError(f"feature line not unique for '{feature}' in section '{section}': found={len(matches)}")
    return matches[0]


def set_feature_state_in_section(
    text: str,
    *,
    section: str,
    feature: str,
    enabled: bool,
) -> str:
    lines = text.splitlines()
    line_idx = find_feature_line_index(text, section=section, feature=feature)
    match = match_feature_line(feature, lines[line_idx])
    if match is None:
        raise ValueError(f"feature line not found for '{feature}' in section '{section}'")
    indent = match.group("indent") or ""
    lines[line_idx] = f"{indent}- {feature}" if enabled else f"{indent}# - {feature}"
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix


def match_feature_line(feature: str, line: str) -> re.Match[str] | None:
    pattern = re.compile(rf"^(?P<indent>\s*)(?P<comment>#\s*)?-\s*{re.escape(feature)}\s*$")
    return pattern.match(line)
