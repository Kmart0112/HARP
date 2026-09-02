from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from harp.controllers import CalibrationMethod, TrainController, TrainCommand, TrainPipelineKind
from harp.shared.logging import configure_logging, get_logger
from harp.shared.paths import ensure_runtime_dirs
from pipeline.jobs._where_parser import parse_where_args
from pipeline.runtime_settings import load_pipeline_runtime_config


@dataclass(frozen=True)
class TrainJobSpec:
    job_name: str
    description: str
    pipeline_kind: TrainPipelineKind
    train_year_start: int
    train_year_end: int
    test_year: int
    feature_set_example: str
    artifact_out: str
    manifest_out: str
    legacy_artifact_out: str
    calibration_method: CalibrationMethod = CalibrationMethod.NONE
    calibration_odds_col: str | None = None


def _build_train_parser(spec: TrainJobSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=spec.description)
    parser.add_argument("--train-year-start", type=int, default=spec.train_year_start)
    parser.add_argument("--train-year-end", type=int, default=spec.train_year_end)
    parser.add_argument("--test-year", type=int, default=spec.test_year)
    parser.add_argument(
        "--feature-set",
        type=str,
        default=None,
        help=(
            "Override feature set name from the feature registry YAML "
            f"(e.g. {spec.feature_set_example})."
        ),
    )
    parser.add_argument(
        "--calibration-method",
        type=str,
        default=spec.calibration_method.value,
        choices=[method.value for method in CalibrationMethod],
        help="Calibration method for post-train step.",
    )
    parser.add_argument(
        "--calibration-odds-col",
        type=str,
        default=spec.calibration_odds_col,
        help="Odds column used for calibration (required for platt_logodds).",
    )
    parser.add_argument("--artifact-out", type=str, default=spec.artifact_out)
    parser.add_argument("--manifest-out", type=str, default=spec.manifest_out)
    parser.add_argument("--legacy-copy", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--legacy-artifact-out", type=str, default=spec.legacy_artifact_out)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--where",
        action="append",
        default=None,
        help="Optional filter in key=value form. Repeatable. Defaults include race_level__neq=0 and race_level__lte=3.",
    )
    return parser


def _build_start_context(spec: TrainJobSpec, args: argparse.Namespace, where_filters: dict[str, object] | None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "pipeline_kind": spec.pipeline_kind.value,
        "train_year_start": int(args.train_year_start),
        "train_year_end": int(args.train_year_end),
        "test_year": int(args.test_year),
        "feature_set": args.feature_set,
        "artifact_out": args.artifact_out,
        "manifest_out": args.manifest_out,
        "legacy_copy": bool(args.legacy_copy),
        "legacy_artifact_out": args.legacy_artifact_out,
        "calibration_method": args.calibration_method,
        "calibration_odds_col": args.calibration_odds_col,
        "limit": args.limit,
        "where": where_filters,
    }
    return context


def _build_command(
    spec: TrainJobSpec,
    args: argparse.Namespace,
    where_filters: dict[str, object] | None,
) -> TrainCommand:
    calibration_method = CalibrationMethod.from_str(str(args.calibration_method))
    return TrainCommand(
        pipeline_kind=spec.pipeline_kind,
        train_year_start=int(args.train_year_start),
        train_year_end=int(args.train_year_end),
        test_year=int(args.test_year),
        artifact_out=args.artifact_out,
        manifest_out=args.manifest_out,
        legacy_copy=bool(args.legacy_copy),
        legacy_artifact_out=args.legacy_artifact_out,
        calibration_method=calibration_method,
        calibration_odds_col=args.calibration_odds_col,
        feature_set_name=args.feature_set,
        limit=args.limit,
        where=where_filters,
    )


def _build_calibration_summary(calibration_info: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "odds_col": calibration_info.get("odds_col"),
        "oof_n": calibration_info.get("oof_n"),
        "oof_missing": calibration_info.get("oof_missing"),
        "oof_fallback_in_sample": calibration_info.get("oof_fallback_in_sample"),
    }
    platt = calibration_info.get("platt")
    if isinstance(platt, dict):
        summary["coef"] = platt.get("coef")
        summary["intercept"] = platt.get("intercept")
    fold_metrics = calibration_info.get("fold_metrics")
    if isinstance(fold_metrics, list):
        summary["fold_count"] = len(fold_metrics)
    return summary


def run_training_job(spec: TrainJobSpec) -> None:
    args = _build_train_parser(spec).parse_args()
    config = load_pipeline_runtime_config()

    configure_logging(config.log_level)
    logger = get_logger(__name__)
    ensure_runtime_dirs()

    where_filters = parse_where_args(args.where)
    context = _build_start_context(spec, args, where_filters)
    logger.info("Starting job=%s params=%s", spec.job_name, context)

    try:
        command = _build_command(spec=spec, args=args, where_filters=where_filters)
        result = TrainController(config).run(command)

        logger.info(
            "%s model trained. rows train=%d val=%d test=%d",
            spec.pipeline_kind.value,
            result.train_rows,
            result.val_rows,
            result.test_rows,
        )
        logger.info("artifact=%s legacy_copy=%s", result.artifact_out, result.legacy_artifact_out)
        logger.info("manifest=%s metrics=%s", result.manifest_out, result.metrics)
        if result.calibration_info is not None:
            logger.info("calibration_summary=%s", _build_calibration_summary(result.calibration_info))
            logger.info("calibration_details=%s", result.calibration_info)
    except Exception:
        logger.exception("Job failed job=%s params=%s", spec.job_name, context)
        raise
