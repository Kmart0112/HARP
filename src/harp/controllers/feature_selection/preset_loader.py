from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harp.shared.paths import project_root


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresetValidationModel(_StrictModel):
    name: str
    category: str
    change_summary: str
    experiment_name: str | None = None


class PresetOutputsModel(_StrictModel):
    report_file: str
    runs_csv_file: str
    decisions_csv_file: str
    selected_contract_file: str
    run_log_dir: str

    @field_validator("report_file", "runs_csv_file", "decisions_csv_file", "selected_contract_file", "run_log_dir")
    @classmethod
    def validate_relative_template(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("output template must not be empty")
        path = Path(normalized)
        if path.is_absolute():
            raise ValueError("output template must be relative")
        if any(part == ".." for part in path.parts):
            raise ValueError("output template must not contain parent traversal")
        return normalized


class PresetAggregateGroupModel(_StrictModel):
    group_id: str
    aggregate_features: list[str] = Field(min_length=1)
    source_features: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_disjoint(self) -> "PresetAggregateGroupModel":
        overlap = set(self.aggregate_features) & set(self.source_features)
        if overlap:
            raise ValueError(f"aggregate_features and source_features must be disjoint: {sorted(overlap)}")
        return self


class PresetVariantGroupModel(_StrictModel):
    group_id: str
    candidates: list[str] = Field(min_length=2)


class PresetSelectionModel(_StrictModel):
    base_feature_set_name: str
    target_contract_path: str
    aggregate_groups: list[PresetAggregateGroupModel] = Field(default_factory=list)
    variant_groups: list[PresetVariantGroupModel] = Field(default_factory=list)

    @field_validator("target_contract_path")
    @classmethod
    def validate_target_contract_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_contract_path must not be empty")
        path = Path(normalized)
        if path.is_absolute():
            raise ValueError("target_contract_path must be relative")
        if any(part == ".." for part in path.parts):
            raise ValueError("target_contract_path must not contain parent traversal")
        return normalized

    @model_validator(mode="after")
    def validate_groups(self) -> "PresetSelectionModel":
        if not self.aggregate_groups and not self.variant_groups:
            raise ValueError("at least one aggregate_groups or variant_groups entry is required")
        aggregate_ids = [group.group_id for group in self.aggregate_groups]
        if len(aggregate_ids) != len(set(aggregate_ids)):
            raise ValueError("aggregate_groups.group_id must be unique")
        variant_ids = [group.group_id for group in self.variant_groups]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("variant_groups.group_id must be unique")
        return self


class PresetReportModel(_StrictModel):
    title: str
    background: str
    hypothesis_lines: list[str] = Field(min_length=1)
    leakage_notes: list[str] = Field(min_length=1)
    implementation_notes: list[str] = Field(min_length=1)


class FeatureSelectionPresetModel(_StrictModel):
    version: int
    validation: PresetValidationModel
    outputs: PresetOutputsModel
    selection: PresetSelectionModel
    report: PresetReportModel

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported preset version")
        return value


def load_feature_selection_preset(preset_name: str) -> FeatureSelectionPresetModel:
    """Load and validate a feature selection preset.

    Args:
        preset_name: Preset name without directory or extension.
    """

    path = resolve_feature_selection_preset_path(preset_name)
    if not path.exists():
        raise FileNotFoundError(f"feature selection preset not found: {preset_name}")

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"feature selection preset must be a mapping: {path}")
    return FeatureSelectionPresetModel.model_validate(doc)


def resolve_feature_selection_preset_path(preset_name: str) -> Path:
    """Resolve a feature selection preset name to its YAML path.

    Args:
        preset_name: Preset name without directory or extension.
    """

    normalized = preset_name.strip()
    if not normalized:
        raise ValueError("preset name is required")
    return project_root() / "notebook" / "config" / "feature_selection_presets" / f"{normalized}.yml"


__all__ = [
    "FeatureSelectionPresetModel",
    "PresetAggregateGroupModel",
    "PresetOutputsModel",
    "PresetReportModel",
    "PresetSelectionModel",
    "PresetValidationModel",
    "PresetVariantGroupModel",
    "load_feature_selection_preset",
    "resolve_feature_selection_preset_path",
]
