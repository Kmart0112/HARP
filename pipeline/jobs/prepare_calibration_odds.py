"""Capture pre-start odds for saved calibration predictions, preserving missing entries."""
import argparse
from dataclasses import asdict
import json

from harp.controllers.calibration import prepare_calibration_odds
from pipeline.runtime_settings import load_pipeline_runtime_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions-report", required=True)
    parser.add_argument("--odds-root", default="pipeline/artifacts/evaluation_odds")
    parser.add_argument("--minutes-before-start", type=int, default=10)
    parser.add_argument("--max-age-seconds", type=float, default=300)
    args = parser.parse_args()
    try:
        result = prepare_calibration_odds(config=load_pipeline_runtime_config(),
            predictions_report=args.predictions_report, odds_root=args.odds_root,
            minutes_before_start=args.minutes_before_start, max_age_seconds=args.max_age_seconds)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
