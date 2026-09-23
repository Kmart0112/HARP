"""Evaluate a fixed NN model on its saved held-out split; does not train or fit."""
import argparse
from dataclasses import asdict
import json

from harp.controllers.training.nn import NnTrainController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--checkpoint-id")
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--input-root", default="pipeline/artifacts/nn_inputs")
    parser.add_argument("--prepared-root", default="pipeline/artifacts/nn_datasets")
    parser.add_argument("--model-root", default="pipeline/artifacts/nn_training")
    args = parser.parse_args()
    try:
        controller = NnTrainController(args.input_root, args.prepared_root, args.model_root, provenance={})
        result = controller.evaluate(args.run_id, split=args.split, device=args.device,
                                     checkpoint_id=args.checkpoint_id, batch_size=args.batch_size)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
