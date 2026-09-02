from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harp.config import HarpRuntimeConfig
from harp.shared.paths import project_root
from harp.usecase.feature_registry import (
    RenderFeatureSetRequest,
    run_render_feature_set_usecase,
)

from .deps import build_render_feature_set_deps as _build_render_feature_set_deps


@dataclass(frozen=True)
class RenderFeatureSetCommand:
    feature_set_name: str
    mode: str = "production"
    registry_path: str | None = None
    output_path: str | None = None


class FeatureSetRenderController:
    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run(self, cmd: RenderFeatureSetCommand):
        registry_path = cmd.registry_path or str(project_root() / self._config.paths.feature_sets_path)
        output_path = None
        if cmd.output_path is not None and cmd.output_path.strip():
            output_path = str(Path(cmd.output_path).expanduser().resolve())
        req = RenderFeatureSetRequest(
            registry_path=str(Path(registry_path).expanduser().resolve()),
            feature_set_name=cmd.feature_set_name.strip(),
            mode=cmd.mode.strip(),
            output_path=output_path,
        )
        return run_render_feature_set_usecase(req, _build_render_feature_set_deps())
