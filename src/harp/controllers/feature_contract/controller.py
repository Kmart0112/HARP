from __future__ import annotations

from dataclasses import dataclass

from harp.usecase import (
    ExportFeatureContractRequest,
    run_export_feature_contract_usecase,
)

from .deps import (
    build_export_feature_contract_deps as _build_export_feature_contract_deps,
)


@dataclass(frozen=True)
class ExportFeatureContractCommand:
    """Command values for exporting one feature contract.

    Args:
        registry_path: Path to the feature registry source.
        feature_set_name: Feature set to export.
        target_path: Contract output path.
        name: Optional explicit contract name.
        dry_run: Build the contract without writing it.
        stdout: Emit the contract body to stdout.
        force: Allow creating or overwriting the target.
        check: Validate whether the target is already up to date.
        validate_name_match: Require the generated contract name to match.
        quiet: Suppress non-essential output.
    """

    registry_path: str
    feature_set_name: str
    target_path: str
    name: str | None
    dry_run: bool
    stdout: bool
    force: bool
    check: bool
    validate_name_match: bool
    quiet: bool


class FeatureContractController:
    """Build feature contract export usecase input from a command."""

    def run(self, cmd: ExportFeatureContractCommand):
        """Export or validate a feature contract.

        Args:
            cmd: CLI-level command values for the contract export.
        """

        req = ExportFeatureContractRequest(
            registry_path=cmd.registry_path,
            feature_set_name=cmd.feature_set_name,
            target_path=cmd.target_path,
            contract_name=cmd.name,
            dry_run=cmd.dry_run,
            emit_stdout=cmd.stdout,
            allow_create=cmd.force,
            check_only=cmd.check,
            validate_name_match=cmd.validate_name_match,
            quiet=cmd.quiet,
        )
        deps = _build_export_feature_contract_deps()
        return run_export_feature_contract_usecase(req, deps)


__all__ = [
    "ExportFeatureContractCommand",
    "FeatureContractController",
]
