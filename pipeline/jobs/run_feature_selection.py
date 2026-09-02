from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

from harp.controllers import FeatureSelectionController, FeatureSelectionCommand
from harp.shared.logging import configure_logging, get_logger
from harp.shared.paths import ensure_runtime_dirs
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature selection job with MLflow tracking.")
    parser.add_argument("--preset", type=str, required=True, help="Feature selection preset name.")
    parser.add_argument("--report-out", type=str, default=None)
    parser.add_argument("--runs-csv-out", type=str, default=None)
    parser.add_argument("--decisions-csv-out", type=str, default=None)
    parser.add_argument("--selected-contract-snapshot-out", type=str, default=None)
    parser.add_argument("--run-log-dir", type=str, default=None)
    parser.add_argument("--git-commit", type=str, default=None)
    parser.add_argument("--resume-parent-run-id", type=str, default=None)
    parser.add_argument("--only-scenarios", type=str, default=None)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--append-note", type=str, default=None)
    parser.add_argument("--write-contract", action="store_true")
    return parser.parse_args()


def _resolve_git_commit(explicit_value: str | None) -> str:
    if explicit_value and explicit_value.strip():
        return explicit_value.strip()
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    args = parse_args()
    if args.finalize and not args.write_contract:
        raise SystemExit("--finalize requires --write-contract")
    if args.write_contract and not args.finalize:
        raise SystemExit("--write-contract requires --finalize")

    config = load_pipeline_runtime_config()
    configure_logging(config.log_level)
    logger = get_logger(__name__)
    ensure_runtime_dirs()

    only_scenarios = ()
    if args.only_scenarios:
        only_scenarios = tuple(part.strip() for part in str(args.only_scenarios).split(",") if part.strip())

    cmd = FeatureSelectionCommand(
        preset=args.preset,
        preset_name=args.preset,
        report_out=args.report_out,
        runs_csv_out=args.runs_csv_out,
        decisions_csv_out=args.decisions_csv_out,
        selected_contract_snapshot_out=args.selected_contract_snapshot_out,
        run_log_dir=args.run_log_dir,
        command=shlex.join(sys.argv),
        git_commit=_resolve_git_commit(args.git_commit),
        resume_parent_run_id=args.resume_parent_run_id,
        only_scenarios=only_scenarios,
        finalize=bool(args.finalize),
        append_note=args.append_note,
        write_contract=bool(args.write_contract),
    )
    logger.info("Starting feature selection preset=%s", args.preset)
    result = FeatureSelectionController(config).run(cmd)
    logger.info(
        "feature selection completed parent_run_id=%s report=%s selected_contract=%s",
        result.parent_run_id,
        result.report_path,
        result.target_contract_path,
    )
    print(f"theme_status={result.theme_status}")
    print(f"theme_revision={result.theme_revision}")
    print(f"contract_written={result.contract_written}")
    print(f"parent_run_id={result.parent_run_id}")
    print(f"report={result.report_path}")
    print(f"runs_csv={result.runs_csv_path}")
    print(f"decisions_csv={result.decisions_csv_path}")
    print(f"selected_contract={result.target_contract_path}")


if __name__ == "__main__":
    main()
