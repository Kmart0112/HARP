from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from harp.config import HarpRuntimeConfig
from harp.core.inference import resolve_date_range
from harp.interface.ports import FileGatewayPort
from harp.usecase.prediction.place import (
    PredictPlaceRequest,
    run_predict_place_usecase,
)

from .deps import build_predict_place_deps as _build_predict_place_deps


@dataclass(frozen=True)
class PredictPlaceCommand:
    """Command values for place-probability prediction.

    Args:
        artifact_path: Model artifact path used for inference.
        manifest_path: Optional manifest path. It can be inferred when omitted.
        from_date: Optional inclusive prediction start date.
        to_date: Optional inclusive prediction end date.
        limit: Optional row limit for prediction input.
        fukusho_type: Odds column used for fukusho expected value.
        edge_threshold: Minimum expected edge included in the result.
        bankroll: Bankroll used for stake sizing.
        kelly_fraction: Fractional Kelly multiplier.
        kelly_cap: Maximum stake fraction per row.
    """

    artifact_path: str
    manifest_path: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    limit: int | None = None
    fukusho_type: str = "odds_fukusho_avg"
    edge_threshold: float = 0.1
    bankroll: float = 100000.0
    kelly_fraction: float = 0.1
    kelly_cap: float = 0.05


def infer_predict_manifest_path(artifact_path: str) -> str | None:
    """Infer the metadata manifest path for a model artifact path.

    Args:
        artifact_path: Model artifact path under the models artifact directory.
    """

    normalized = str(Path(artifact_path).as_posix())
    key = "pipeline/artifacts/models/"
    if key not in normalized:
        return None
    mapped = normalized.replace(key, "pipeline/artifacts/metadata/", 1)
    return str(Path(mapped).with_suffix(".json").as_posix())


def resolve_predict_manifest_path(
    *,
    artifact_path: str,
    manifest_path: str | None,
    file_gateway: FileGatewayPort,
) -> str | None:
    """Resolve the manifest path from explicit input or artifact conventions.

    Args:
        artifact_path: Model artifact path used when inferring a manifest path.
        manifest_path: Optional explicit manifest path.
        file_gateway: File gateway used to check inferred manifest existence.
    """

    if manifest_path is not None and str(manifest_path).strip():
        return str(manifest_path).strip()

    inferred = infer_predict_manifest_path(artifact_path)
    if inferred is not None and file_gateway.exists(inferred):
        return inferred
    return None


class PredictController:
    """Build prediction usecase input from a place prediction command."""

    def __init__(self, config: HarpRuntimeConfig) -> None:
        self._config = config

    def run_place(self, cmd: PredictPlaceCommand):
        """Run place-probability prediction.

        Args:
            cmd: CLI-level command values for prediction.
        """

        deps = _build_predict_place_deps(self._config)
        from_date, to_date = resolve_date_range(
            cmd.from_date,
            cmd.to_date,
            now=datetime.now(),
        )
        req = PredictPlaceRequest(
            artifact_path=cmd.artifact_path,
            manifest_path=resolve_predict_manifest_path(
                artifact_path=cmd.artifact_path,
                manifest_path=cmd.manifest_path,
                file_gateway=deps.file_gateway,
            ),
            from_date=from_date,
            to_date=to_date,
            limit=cmd.limit,
            fukusho_type=cmd.fukusho_type,
            edge_threshold=cmd.edge_threshold,
            bankroll=cmd.bankroll,
            kelly_fraction=cmd.kelly_fraction,
            kelly_cap=cmd.kelly_cap,
        )
        return run_predict_place_usecase(req=req, deps=deps)
