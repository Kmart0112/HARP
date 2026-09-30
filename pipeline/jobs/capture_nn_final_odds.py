"""Capture final place-odds teachers for the entrants of a saved NN Dataset."""
import argparse
import json
from dataclasses import asdict

from harp.controllers.nn_dataset.odds import (
    CaptureNnFinalOddsCommand,
    NnFinalOddsController,
)
from pipeline.runtime_settings import load_pipeline_env_files, resolve_database_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-dataset-id", required=True)
    parser.add_argument("--input-root", default="pipeline/artifacts/nn_inputs")
    parser.add_argument("--prepared-root", default="pipeline/artifacts/nn_datasets")
    parser.add_argument("--output-root", default="pipeline/artifacts/nn_odds")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    try:
        load_pipeline_env_files()
        controller = NnFinalOddsController(input_root=args.input_root, prepared_root=args.prepared_root,
                                           output_root=args.output_root, db_url=resolve_database_url())
        result = controller.run(CaptureNnFinalOddsCommand(args.prepared_dataset_id, args.batch_size))
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
