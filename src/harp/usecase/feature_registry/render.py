from __future__ import annotations

from dataclasses import dataclass

from harp.interface.ports import FeatureDefinitionPort, FileGatewayPort


@dataclass(frozen=True)
class RenderFeatureSetRequest:
    registry_path: str
    feature_set_name: str
    mode: str
    output_path: str | None


@dataclass(frozen=True)
class RenderFeatureSetDeps:
    file_gateway: FileGatewayPort
    feature_definition_port: FeatureDefinitionPort


@dataclass(frozen=True)
class RenderFeatureSetResult:
    registry_path: str
    feature_set_name: str
    feature_names: tuple[str, ...]
    cat_features: tuple[str, ...]
    rendered_text: str
    output_path: str | None


def run_render_feature_set_usecase(
    req: RenderFeatureSetRequest,
    deps: RenderFeatureSetDeps,
) -> RenderFeatureSetResult:
    feature_set = deps.feature_definition_port.load_feature_set(
        source_path=req.registry_path,
        feature_set_name=req.feature_set_name,
        mode=req.mode,
    )
    rendered = deps.feature_definition_port.render_feature_config(
        feature_names=list(feature_set.feature_names),
        cat_features=list(feature_set.cat_features),
    )
    if req.output_path is not None:
        deps.file_gateway.write_text(req.output_path, rendered)
    return RenderFeatureSetResult(
        registry_path=req.registry_path,
        feature_set_name=req.feature_set_name,
        feature_names=feature_set.feature_names,
        cat_features=feature_set.cat_features,
        rendered_text=rendered,
        output_path=req.output_path,
    )
