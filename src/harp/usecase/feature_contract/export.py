from __future__ import annotations

from pathlib import Path

from .dto import (
    ExportFeatureContractDeps,
    ExportFeatureContractRequest,
    ExportFeatureContractResult,
)


class FeatureContractCheckMismatchError(ValueError):
    """Raised when --check detects a mismatch against the target contract."""


def _derive_contract_name(target_path: str, explicit_name: str | None) -> str:
    if explicit_name is not None and explicit_name.strip():
        return explicit_name.strip()
    return Path(target_path).stem


def run_export_feature_contract_usecase(
    req: ExportFeatureContractRequest,
    deps: ExportFeatureContractDeps,
) -> ExportFeatureContractResult:
    file_gateway = deps.file_gateway

    if not file_gateway.exists(req.registry_path):
        raise FileNotFoundError(f"registry not found: {req.registry_path}")

    target_exists = file_gateway.exists(req.target_path)
    if not target_exists and not req.allow_create:
        raise ValueError(f"target does not exist; pass --force to create: {req.target_path}")

    contract_name = _derive_contract_name(req.target_path, req.contract_name)
    target_stem = Path(req.target_path).stem
    if req.validate_name_match and contract_name != target_stem:
        raise ValueError(
            f"contract name does not match target stem: {contract_name} != {target_stem}"
        )

    feature_set = deps.feature_definition_port.load_feature_set(
        source_path=req.registry_path,
        feature_set_name=req.feature_set_name,
        mode="production",
    )
    feature_names = list(feature_set.feature_names)
    cat_features = list(feature_set.cat_features)
    yaml_text = deps.feature_definition_port.render_contract(
        contract_name=contract_name,
        feature_names=feature_names,
        cat_features=cat_features,
    )

    changed = True
    created = not target_exists
    added_features = list(feature_names)
    removed_features: list[str] = []

    if target_exists:
        existing_text = file_gateway.read_text(req.target_path)
        changed = existing_text != yaml_text

        existing_features = deps.feature_definition_port.parse_contract_text(
            existing_text,
            source=req.target_path,
        )
        if existing_features is not None:
            existing_feature_names = list(existing_features.feature_names)
            existing_feature_set = set(existing_feature_names)
            new_feature_set = set(feature_names)
            added_features = [feature for feature in feature_names if feature not in existing_feature_set]
            removed_features = [
                feature for feature in existing_feature_names if feature not in new_feature_set
            ]
        else:
            added_features = []
            removed_features = []

    if req.check_only:
        if changed:
            raise FeatureContractCheckMismatchError(
                f"target contract differs from generated output: {req.target_path}"
            )
        return ExportFeatureContractResult(
            target_path=req.target_path,
            contract_name=contract_name,
            feature_names=feature_names,
            cat_features=cat_features,
            changed=False,
            created=False,
            check_only=True,
            yaml_text=yaml_text,
            added_features=added_features,
            removed_features=removed_features,
        )

    if not req.dry_run:
        file_gateway.write_text(req.target_path, yaml_text)

    return ExportFeatureContractResult(
        target_path=req.target_path,
        contract_name=contract_name,
        feature_names=feature_names,
        cat_features=cat_features,
        changed=changed,
        created=created,
        check_only=False,
        yaml_text=yaml_text,
        added_features=added_features,
        removed_features=removed_features,
    )


__all__ = [
    "FeatureContractCheckMismatchError",
    "run_export_feature_contract_usecase",
]
