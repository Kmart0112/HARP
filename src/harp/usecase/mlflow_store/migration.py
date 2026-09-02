from __future__ import annotations

from pathlib import Path

from .dto import (
    MlflowStoreMigrationDeps,
    MlflowStoreMigrationRequest,
    MlflowStoreMigrationResult,
)


def run_migrate_mlflow_store_usecase(
    req: MlflowStoreMigrationRequest,
    deps: MlflowStoreMigrationDeps,
) -> MlflowStoreMigrationResult:
    file_gateway = deps.file_gateway
    target_store_dir = deps.mlflow_store_port.resolve_local_store_dir(req.target_tracking_uri)
    if target_store_dir is None:
        raise ValueError("mlflow store migration only supports local file tracking URIs.")

    source_dir = str(Path(req.source_store_dir).resolve())
    target_dir = str(Path(target_store_dir).resolve())
    if source_dir == target_dir:
        raise ValueError("source and target MLflow stores must be different directories.")
    if not file_gateway.exists(source_dir):
        raise FileNotFoundError(f"source MLflow store not found: {source_dir}")

    source_files = _relative_files(file_gateway.list_files(source_dir), source_dir)
    target_files = _relative_files(file_gateway.list_files(target_dir), target_dir) if file_gateway.exists(target_dir) else {}
    source_dirs = _relative_dirs(file_gateway.list_dirs(source_dir), source_dir)

    copied_files: list[str] = []
    rewritten_meta_files: list[str] = []
    conflicts: list[str] = []

    for rel_dir in source_dirs:
        if req.check_only:
            continue
        file_gateway.make_dir(str(Path(target_dir) / rel_dir))

    for rel_path, source_path in source_files.items():
        target_path = str(Path(target_dir) / rel_path)
        existing_target_path = target_files.get(rel_path)

        if _is_rewritable_meta(rel_path):
            source_text = file_gateway.read_text(source_path)
            desired_text = deps.mlflow_store_port.rewrite_meta_for_target(
                rel_path=rel_path,
                source_text=source_text,
                target_store_dir=target_dir,
            )
            if existing_target_path is not None:
                current_text = file_gateway.read_text(existing_target_path)
                if current_text not in {source_text, desired_text}:
                    conflicts.append(rel_path)
                    continue
            if existing_target_path is None or file_gateway.read_text(existing_target_path) != desired_text:
                rewritten_meta_files.append(rel_path)
                if not req.check_only:
                    file_gateway.write_text(target_path, desired_text)
            continue

        if existing_target_path is None:
            copied_files.append(rel_path)
            if not req.check_only:
                file_gateway.copy(source_path, target_path)
            continue

        if file_gateway.read_bytes(source_path) != file_gateway.read_bytes(existing_target_path):
            conflicts.append(rel_path)

    if conflicts:
        raise ValueError(f"mlflow store migration conflict: {', '.join(conflicts[:5])}")

    verification = (
        deps.mlflow_store_port.verify_store_readable(req.target_tracking_uri)
        if not req.check_only
        else None
    )
    return MlflowStoreMigrationResult(
        source_store_dir=source_dir,
        target_store_dir=target_dir,
        target_tracking_uri=req.target_tracking_uri,
        check_only=req.check_only,
        copied_files=tuple(copied_files),
        rewritten_meta_files=tuple(rewritten_meta_files),
        verified_experiment_names=() if verification is None else verification.experiment_names,
    )


def _relative_files(files: list[str], base_dir: str) -> dict[str, str]:
    base = Path(base_dir).resolve()
    return {str(Path(path).resolve().relative_to(base)): path for path in files}


def _relative_dirs(dirs: list[str], base_dir: str) -> tuple[str, ...]:
    base = Path(base_dir).resolve()
    return tuple(
        str(Path(path).resolve().relative_to(base))
        for path in dirs
        if str(Path(path).resolve().relative_to(base)) not in {"", "."}
    )


def _is_rewritable_meta(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    if not parts or parts[-1] != "meta.yaml":
        return False
    if parts[0] in {"models", ".trash"}:
        return False
    if len(parts) == 2 and parts[0].isdigit():
        return True
    if len(parts) == 3 and parts[0].isdigit():
        return True
    return False
