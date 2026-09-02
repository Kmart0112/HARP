from __future__ import annotations

import argparse
from pathlib import Path

from harp.controllers import (
    ExportFeatureContractCommand,
    FeatureContractCheckMismatchError,
    FeatureContractController,
)
from harp.shared.paths import project_root
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a registry feature set into a pipeline feature contract YAML.",
    )
    parser.add_argument(
        "--feature-set",
        type=str,
        required=True,
        help="Feature set name defined in the centralized feature registry.",
    )
    parser.add_argument(
        "--registry",
        type=str,
        default=None,
        help="Source feature registry path.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="contracts/features/place/place_v1.yaml",
        help="Target contract YAML path under contracts/features.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional contract name. Defaults to target file stem.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render and diff without writing the target file.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Always print generated YAML to stdout.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow creating a new target contract file when it does not exist.",
    )
    parser.add_argument(
        "--validate-name-match",
        action="store_true",
        help="Require contract name to match target file stem.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if target differs from generated output.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success summary output.",
    )
    return parser.parse_args()


def _resolve_project_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str(project_root() / candidate)


def _print_summary(result, *, dry_run: bool) -> None:  # noqa: ANN001
    status = "check_ok" if result.check_only else "dry_run" if dry_run else "updated"
    if result.created and not dry_run:
        status = "created"
    elif not result.changed and not result.check_only:
        status = "unchanged"
    print(
        f"status={status} target={result.target_path} name={result.contract_name} "
        f"feature_count={len(result.feature_names)} cat_feature_count={len(result.cat_features)}"
    )
    print(
        f"diff_summary added={len(result.added_features)} removed={len(result.removed_features)}"
    )
    if result.added_features:
        print("added_features=" + ",".join(result.added_features))
    if result.removed_features:
        print("removed_features=" + ",".join(result.removed_features))


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()
    registry_path = args.registry or _resolve_project_path(config.paths.feature_sets_path)
    command = ExportFeatureContractCommand(
        registry_path=registry_path,
        feature_set_name=args.feature_set,
        target_path=args.target,
        name=args.name,
        dry_run=bool(args.dry_run),
        stdout=bool(args.stdout),
        force=bool(args.force),
        check=bool(args.check),
        validate_name_match=bool(args.validate_name_match),
        quiet=bool(args.quiet),
    )
    try:
        result = FeatureContractController().run(command)
    except FeatureContractCheckMismatchError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        raise SystemExit(2) from exc

    if args.stdout or args.dry_run:
        print(result.yaml_text, end="" if result.yaml_text.endswith("\n") else "\n")

    if not args.quiet:
        _print_summary(result, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    main()
