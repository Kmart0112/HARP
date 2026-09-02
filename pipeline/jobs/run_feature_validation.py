from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

from harp.controllers import FeatureValidationController, FeatureValidationCommand
from harp.shared.logging import configure_logging, get_logger
from harp.shared.paths import ensure_runtime_dirs
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature validation job with MLflow tracking.")
    parser.add_argument(
        "--preset",
        type=str,
        default="raw_course_features",
        help="Feature validation preset name.",
    )
    parser.add_argument("--report-out", type=str, default=None)
    parser.add_argument("--runs-csv-out", type=str, default=None)
    parser.add_argument("--run-log-dir", type=str, default=None)
    parser.add_argument("--git-commit", type=str, default=None)
    parser.add_argument("--resume-parent-run-id", type=str, default=None)
    parser.add_argument("--only-scenarios", type=str, default=None)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--final-selected-scenario", type=str, default=None)
    parser.add_argument("--append-note", type=str, default=None)
    return parser.parse_args()


def _resolve_git_commit(explicit_value: str | None) -> str:
    if explicit_value and explicit_value.strip():
        return explicit_value.strip()
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
            .strip()
        )
    except Exception:
        return "unknown"


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()
    configure_logging(config.log_level)
    logger = get_logger(__name__)
    ensure_runtime_dirs()

    only_scenarios = ()
    if args.only_scenarios:
        only_scenarios = tuple(part.strip() for part in str(args.only_scenarios).split(",") if part.strip())

    command_line = shlex.join(sys.argv)
    cmd = FeatureValidationCommand(
        preset=args.preset,
        preset_name=args.preset,
        report_out=args.report_out,
        runs_csv_out=args.runs_csv_out,
        run_log_dir=args.run_log_dir,
        command=command_line,
        git_commit=_resolve_git_commit(args.git_commit),
        resume_parent_run_id=args.resume_parent_run_id,
        only_scenarios=only_scenarios,
        finalize=bool(args.finalize),
        final_selected_scenario=args.final_selected_scenario,
        append_note=args.append_note,
    )
    logger.info("Starting feature validation preset=%s", args.preset)
    result = FeatureValidationController(config).run(cmd)
    logger.info(
        "feature validation completed decision=%s parent_run_id=%s report=%s",
        result.decision,
        result.parent_run_id,
        result.report_path,
    )
    print(f"decision={result.decision}")
    print(f"theme_status={result.theme_status}")
    print(f"theme_revision={result.theme_revision}")
    print(f"parent_run_id={result.parent_run_id}")
    print(f"report={result.report_path}")
    print(f"runs_csv={result.runs_csv_path}")


if __name__ == "__main__":
    main()
