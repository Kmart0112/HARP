from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harp.shared.paths import project_root


ValidationMode = Literal["baseline", "single_add", "feature_set_add", "replace_existing"]


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
    run_log_dir: str

    @field_validator("report_file", "runs_csv_file", "run_log_dir")
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


class PresetReportModel(_StrictModel):
    title: str
    background: str
    hypothesis_lines: list[str] = Field(min_length=1)
    leakage_notes: list[str] = Field(min_length=1)
    implementation_notes: list[str] = Field(min_length=1)
    metrics_notebook_path: str
    shap_notebook_path: str


class PresetTargetFeatureModel(_StrictModel):
    feature_name: str
    feature_type: str
    change_type: str
    summary: str
    sections: list[str] = Field(min_length=1)
    comparison_features: list[str] = Field(default_factory=list)
    dbt_model_path: str = ""
    dbt_yaml_path: str = ""
    final_column: str = ""


class PresetToggleModel(_StrictModel):
    feature_name: str
    sections: list[str] = Field(min_length=1)
    enabled: bool


class PresetFeatureSetModel(_StrictModel):
    base_feature_set_name: str
    include_features: list[str] = Field(default_factory=list)
    exclude_features: list[str] = Field(default_factory=list)
    include_cat_features: list[str] = Field(default_factory=list)
    exclude_cat_features: list[str] = Field(default_factory=list)


class PresetShapModel(_StrictModel):
    candidate_feature: str
    comparison_features: list[str] = Field(min_length=1)
    report_run_label: str


class PresetScenarioModel(_StrictModel):
    scenario_name: str
    validation_mode: ValidationMode
    toggles: list[PresetToggleModel] = Field(default_factory=list)
    feature_set: PresetFeatureSetModel | None = None
    shap: PresetShapModel | None = None

    @model_validator(mode="after")
    def validate_single_add_shap_shape(self) -> "PresetScenarioModel":
        if self.scenario_name != "baseline_existing" and not self.toggles and self.feature_set is None:
            raise ValueError("scenario must define toggles or feature_set")
        if self.shap is None:
            return self
        if self.validation_mode != "single_add":
            return self
        enabled_features = [toggle.feature_name for toggle in self.toggles if toggle.enabled]
        if self.feature_set is not None:
            if self.shap.candidate_feature not in self.feature_set.include_features:
                raise ValueError(
                    "single_add scenario with feature_set + SHAP must include shap.candidate_feature"
                )
            return self
        if enabled_features != [self.shap.candidate_feature]:
            raise ValueError(
                "single_add scenario with SHAP must enable exactly one feature matching shap.candidate_feature"
            )
        return self


class FeatureValidationPresetModel(_StrictModel):
    version: int
    validation: PresetValidationModel
    outputs: PresetOutputsModel
    report: PresetReportModel
    target_features: list[PresetTargetFeatureModel] = Field(min_length=1)
    scenarios: list[PresetScenarioModel] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported preset version")
        return value

    @model_validator(mode="after")
    def validate_cross_references(self) -> "FeatureValidationPresetModel":
        feature_names = [feature.feature_name for feature in self.target_features]
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("target_features.feature_name must be unique")

        scenario_names = [scenario.scenario_name for scenario in self.scenarios]
        if len(scenario_names) != len(set(scenario_names)):
            raise ValueError("scenario_name must be unique")
        if self.scenarios[0].scenario_name != "baseline_existing":
            raise ValueError("first scenario must be baseline_existing")

        target_feature_set = set(feature_names)
        for scenario in self.scenarios:
            for toggle in scenario.toggles:
                if not toggle.sections:
                    raise ValueError("toggle.sections must not be empty")
            if scenario.shap is not None and scenario.shap.candidate_feature not in target_feature_set:
                raise ValueError("shap.candidate_feature must exist in target_features")
        return self


def load_feature_validation_preset(preset_name: str) -> FeatureValidationPresetModel:
    """Load and validate a feature validation preset.

    Args:
        preset_name: Preset name without directory or extension.
    """

    path = resolve_feature_validation_preset_path(preset_name)
    if not path.exists():
        raise FileNotFoundError(f"feature validation preset not found: {preset_name}")

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"feature validation preset must be a mapping: {path}")
    return FeatureValidationPresetModel.model_validate(doc)


def resolve_feature_validation_preset_path(preset_name: str) -> Path:
    """Resolve a feature validation preset name to its YAML path.

    Args:
        preset_name: Preset name without directory or extension.
    """

    normalized = preset_name.strip()
    if not normalized:
        raise ValueError("preset name is required")
    return project_root() / "notebook" / "config" / "feature_validation_presets" / f"{normalized}.yml"


__all__ = [
    "FeatureValidationPresetModel",
    "PresetReportModel",
    "PresetFeatureSetModel",
    "PresetScenarioModel",
    "PresetShapModel",
    "PresetTargetFeatureModel",
    "PresetToggleModel",
    "PresetValidationModel",
    "load_feature_validation_preset",
    "resolve_feature_validation_preset_path",
]
