from __future__ import annotations

import argparse
from pathlib import Path

from harp.controllers import PredictController, PredictPlaceCommand
from harp.shared.logging import configure_logging, get_logger
from harp.shared.paths import ensure_runtime_dirs
from pipeline.runtime_settings import (
    load_pipeline_runtime_config,
    load_predict_runtime_defaults,
)


def _parse_non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0.0:
        raise argparse.ArgumentTypeError(f"Expected non-negative float, got {raw!r}")
    return value


def _parse_unit_interval_float(raw: str) -> float:
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError(f"Expected float in [0.0, 1.0], got {raw!r}")
    return value


def parse_args() -> argparse.Namespace:
    predict_defaults = load_predict_runtime_defaults()
    parser = argparse.ArgumentParser(
        description="Run place inference and output race entries/edge candidates CSVs.",
    )
    parser.add_argument(
        "--artifact",
        type=str,
        default="pipeline/artifacts/models/is_place_platt_v1.pkl",
        help=(
            "Path to place model artifact pickle. "
            "Default uses Platt-calibrated model."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=None,
        help="Optional model manifest JSON path. If omitted, inferred from artifact path.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="pipeline/outputs/race_entries.csv",
        help="Output CSV path for all race entries.",
    )
    parser.add_argument(
        "--edge-out",
        type=str,
        default="pipeline/outputs/edge_candidates.csv",
        help="Output CSV path for edge candidates.",
    )
    parser.add_argument(
        "--shift-out",
        type=str,
        default="pipeline/outputs/race_entries_platt_shift.csv",
        help="Output CSV path for Platt+logit-shift race entries.",
    )
    parser.add_argument(
        "--shift-edge-out",
        type=str,
        default="pipeline/outputs/edge_candidates_platt_shift.csv",
        help="Output CSV path for Platt+logit-shift edge candidates.",
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default=None,
        help="Filter held_date >= YYYY-MM-DD",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=None,
        help="Filter held_date <= YYYY-MM-DD",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max rows for feature loading.",
    )
    parser.add_argument(
        "--fukusho-type",
        type=str,
        default="odds_fukusho_avg",
        choices=[
            "odds_fukusho_low",
            "odds_fukusho_high",
            "odds_fukusho_avg",
            "odds_fukusho_weighted_avg",
        ],
        help="Odds column used for EV calculation.",
    )
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=0.1,
        help="Keep rows with edge >= threshold in edge output.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=predict_defaults.bankroll,
        help=(
            "Bankroll used to compute kelly_bet_amount. "
            "Default from HARP_PREDICT_FUKUSHO_BANKROLL or 223000.0."
        ),
    )
    parser.add_argument(
        "--kelly-fraction",
        type=_parse_non_negative_float,
        default=predict_defaults.kelly_fraction,
        help=(
            "Fractional Kelly multiplier. "
            "Priority: CLI > env > default. "
            "Default from HARP_PREDICT_FUKUSHO_KELLY_FRACTION or 0.1."
        ),
    )
    parser.add_argument(
        "--kelly-cap",
        type=_parse_unit_interval_float,
        default=predict_defaults.kelly_cap,
        help=(
            "Upper cap for kelly_fraction. "
            "Priority: CLI > env > default. "
            "Default from HARP_PREDICT_FUKUSHO_KELLY_CAP or 0.05."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()

    configure_logging(level=config.log_level)
    logger = get_logger(__name__)
    ensure_runtime_dirs()

    logger.info(
        "Starting job=run_predict artifact=%s from_date=%s to_date=%s limit=%s fukusho_type=%s "
        "edge_threshold=%.6f bankroll=%.2f kelly_fraction=%.6f kelly_cap=%.6f "
        "manifest=%s out=%s edge_out=%s shift_out=%s shift_edge_out=%s",
        args.artifact,
        args.from_date,
        args.to_date,
        args.limit,
        args.fukusho_type,
        args.edge_threshold,
        args.bankroll,
        args.kelly_fraction,
        args.kelly_cap,
        args.manifest,
        args.out,
        args.edge_out,
        args.shift_out,
        args.shift_edge_out,
    )

    try:
        command = PredictPlaceCommand(
            artifact_path=args.artifact,
            manifest_path=args.manifest,
            from_date=args.from_date,
            to_date=args.to_date,
            limit=args.limit,
            fukusho_type=args.fukusho_type,
            edge_threshold=args.edge_threshold,
            bankroll=args.bankroll,
            kelly_fraction=args.kelly_fraction,
            kelly_cap=args.kelly_cap,
        )
        result = PredictController(config).run_place(command)

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        result.race_entries.to_csv(out_path, index=False)

        edge_out_path = Path(args.edge_out)
        edge_out_path.parent.mkdir(parents=True, exist_ok=True)
        result.edge_candidates.to_csv(edge_out_path, index=False)

        if result.shifted_race_entries is not None:
            shift_out_path = Path(args.shift_out)
            shift_out_path.parent.mkdir(parents=True, exist_ok=True)
            result.shifted_race_entries.to_csv(shift_out_path, index=False)
        else:
            shift_out_path = None

        if result.shifted_edge_candidates is not None:
            shift_edge_out_path = Path(args.shift_edge_out)
            shift_edge_out_path.parent.mkdir(parents=True, exist_ok=True)
            result.shifted_edge_candidates.to_csv(shift_edge_out_path, index=False)
        else:
            shift_edge_out_path = None

        logger.info(
            "Predict range resolved: from_date=%s to_date=%s",
            result.from_date,
            result.to_date,
        )
        logger.info("Wrote race entries: rows=%d path=%s", len(result.race_entries), out_path)
        logger.info(
            "Wrote edge candidates: rows=%d threshold=%.6f path=%s",
            len(result.edge_candidates),
            args.edge_threshold,
            edge_out_path,
        )
        if shift_out_path is not None and result.shifted_race_entries is not None:
            logger.info(
                "Wrote shifted race entries: rows=%d path=%s",
                len(result.shifted_race_entries),
                shift_out_path,
            )
        if shift_edge_out_path is not None and result.shifted_edge_candidates is not None:
            logger.info(
                "Wrote shifted edge candidates: rows=%d threshold=%.6f path=%s",
                len(result.shifted_edge_candidates),
                args.edge_threshold,
                shift_edge_out_path,
            )
    except Exception:
        logger.exception(
            "Job failed job=run_predict artifact=%s from_date=%s to_date=%s limit=%s fukusho_type=%s "
            "edge_threshold=%.6f bankroll=%.2f kelly_fraction=%.6f kelly_cap=%.6f "
            "manifest=%s out=%s edge_out=%s shift_out=%s shift_edge_out=%s",
            args.artifact,
            args.from_date,
            args.to_date,
            args.limit,
            args.fukusho_type,
            args.edge_threshold,
            args.bankroll,
            args.kelly_fraction,
            args.kelly_cap,
            args.manifest,
            args.out,
            args.edge_out,
            args.shift_out,
            args.shift_edge_out,
        )
        raise


if __name__ == "__main__":
    main()
