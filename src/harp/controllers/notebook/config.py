from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root

from .deps import (
    NotebookFeatureConfigDeps,
)
from .deps import (
    build_notebook_feature_config_deps as _build_notebook_feature_config_deps,
)


def build_notebook_config(
    model_cls: type[BaseModel],
    *,
    defaults: BaseModel | dict[str, Any] | None = None,
    cli_args: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> BaseModel:
    """Normalize notebook defaults, CLI arguments, and UI overrides."""

    data: dict[str, Any] = {}
    if defaults is not None:
        if isinstance(defaults, BaseModel):
            data.update(defaults.model_dump())
        else:
            data.update(dict(defaults))
    if cli_args:
        for key, value in cli_args.items():
            normalized_key = str(key).replace("-", "_")
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            data[normalized_key] = value
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                data[key] = value
    return model_cls(**data)


class NotebookFeatureConfigController:
    """Resolve notebook feature inputs through the same runtime configuration as jobs."""

    def __init__(
        self,
        config: HarpRuntimeConfig,
        *,
        deps: NotebookFeatureConfigDeps | None = None,
    ) -> None:
        self._config = config
        self._deps = deps or _build_notebook_feature_config_deps()

    def default_registry_path(self) -> str:
        return str((project_root() / self._config.paths.feature_sets_path).resolve())

    def resolve_feature_set(
        self,
        *,
        feature_set_name: str,
        registry_path: str | None = None,
        mode: str = "production",
        resolved_features_config_path: str | None = None,
    ) -> tuple[str, list[str], list[str]]:
        if resolved_features_config_path is not None and str(resolved_features_config_path).strip():
            config_path = str(Path(str(resolved_features_config_path).strip()).expanduser().resolve())
            feature_set = self._deps.feature_definition_port.parse_feature_config_text(
                self._deps.file_gateway.read_text(config_path),
                source=config_path,
            )
            return config_path, list(feature_set.feature_names), list(feature_set.cat_features)

        resolved_feature_set_name = str(feature_set_name).strip()
        if not resolved_feature_set_name:
            raise ValueError("feature_set_name is required.")

        resolved_registry_path = str(registry_path).strip() if registry_path is not None else ""
        if not resolved_registry_path:
            resolved_registry_path = self.default_registry_path()
        else:
            resolved_registry_path = str(Path(resolved_registry_path).expanduser().resolve())

        feature_set = self._deps.feature_definition_port.load_feature_set(
            source_path=resolved_registry_path,
            feature_set_name=resolved_feature_set_name,
            mode=mode,
        )
        return (
            resolved_registry_path,
            list(feature_set.feature_names),
            list(feature_set.cat_features),
        )
