"""Train the race-history Transformer from an immutable prepared Dataset."""
import argparse
from dataclasses import asdict
import json

from harp.controllers.training.nn import NnTrainCommand, NnTrainController
from pipeline.runtime_settings import collect_nn_training_provenance, load_nn_tracking_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--recipe", default="pipeline/config/nn_training/place_history_set_v1.yml")
    parser.add_argument("--set", action="append", default=[], dest="overrides", help="Explicit section.field=value override")
    parser.add_argument("--resume-run-id", help="Continue a completed epoch into a new run; only max_epochs may change")
    parser.add_argument("--input-root", default="pipeline/artifacts/nn_inputs")
    parser.add_argument("--prepared-root", default="pipeline/artifacts/nn_datasets")
    parser.add_argument("--model-root", default="pipeline/artifacts/nn_training")
    parser.add_argument("--tracking", action="store_true", help="Opt in to MLflow using existing pipeline settings")
    args = parser.parse_args()
    try:
        uri, experiment = load_nn_tracking_settings() if args.tracking else (None, None)
        controller = NnTrainController(args.input_root, args.prepared_root, args.model_root,
                                       provenance=collect_nn_training_provenance(), tracking_uri=uri, tracking_experiment=experiment)
        result = controller.run(NnTrainCommand(args.dataset_id, args.recipe, tuple(args.overrides), args.resume_run_id))
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
