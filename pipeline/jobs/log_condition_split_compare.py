from __future__ import annotations

import argparse
from harp.controllers import (
    ConditionSplitCompareTrackingController,
    ConditionSplitCompareTrackingCommand,
)
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log condition split compare CSV outputs to MLflow.")
    parser.add_argument("--summary-csv", type=str, required=True)
    parser.add_argument("--slices-csv", type=str, required=True)
    parser.add_argument("--experiment-name", type=str, default="condition_split_compare")
    parser.add_argument("--run-name", type=str, default=None)
    parser.add_argument("--parent-run-id", type=str, default=None)
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Repeatable tag in key=value form.",
    )
    return parser.parse_args()


def _parse_tags(raw_tags: list[str]) -> dict[str, str]:
    tags: dict[str, str] = {}
    for raw_tag in raw_tags:
        key, separator, value = str(raw_tag).partition("=")
        if not separator or not key.strip():
            raise ValueError(f"invalid tag, expected key=value: {raw_tag}")
        tags[key.strip()] = value.strip()
    return tags


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()
    result = ConditionSplitCompareTrackingController(config).run(
        ConditionSplitCompareTrackingCommand(
            summary_csv_path=args.summary_csv,
            slices_csv_path=args.slices_csv,
            experiment_name=args.experiment_name,
            run_name=args.run_name,
            parent_run_id=args.parent_run_id,
            tags=_parse_tags(list(args.tags)),
        ),
    )
    print(f"run_id={result.run_id}")
    print(f"experiment_name={result.experiment_name}")
    print(f"run_name={result.run_name}")
    print(f"summary_csv={result.summary_csv_path}")
    print(f"slices_csv={result.slices_csv_path}")
    print(f"slice_count={result.slice_count}")


if __name__ == "__main__":
    main()
