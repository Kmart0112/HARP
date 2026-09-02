from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harp.interface.ports import ArtifactStorePort, ManifestStorePort


@dataclass(frozen=True)
class NotebookModelArtifactSaveRequest:
    payload: dict[str, Any]
    model_type: str
    artifact_out: str
    manifest_out: str
    feature_names: list[str]
    cat_features: list[str]
    train_year_start: int
    train_year_end: int
    test_year: int
    metrics: dict[str, float | None]
    source_table: str
    note: str
    calibration_method: str = "none"


@dataclass(frozen=True)
class NotebookModelArtifactSaveDeps:
    artifact_store_port: ArtifactStorePort
    manifest_store_port: ManifestStorePort


@dataclass(frozen=True)
class NotebookModelArtifactSaveResult:
    artifact_out: str
    manifest_out: str


def run_export_notebook_model_artifact_usecase(
    req: NotebookModelArtifactSaveRequest,
    deps: NotebookModelArtifactSaveDeps,
) -> NotebookModelArtifactSaveResult:
    deps.artifact_store_port.save_artifact(req.payload, req.artifact_out)

    note_with_calibration = req.note
    if req.calibration_method and req.calibration_method != "none":
        note_with_calibration = f"{req.note} | calibration={req.calibration_method}"

    manifest = deps.manifest_store_port.build_manifest(
        model_type=req.model_type,
        artifact_path=req.artifact_out,
        feature_names=req.feature_names,
        cat_features=req.cat_features,
        train_window={
            "train_year_start": int(req.train_year_start),
            "train_year_end": int(req.train_year_end),
            "test_year": int(req.test_year),
        },
        metrics=req.metrics,
        source_table=req.source_table,
        note=note_with_calibration,
    )
    deps.manifest_store_port.validate_manifest(manifest)
    deps.manifest_store_port.write_manifest(manifest, req.manifest_out)

    return NotebookModelArtifactSaveResult(
        artifact_out=req.artifact_out,
        manifest_out=req.manifest_out,
    )
