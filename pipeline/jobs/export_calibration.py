"""Export a calibration curve from a frozen model and labelled dataset, without fitting."""
import argparse
import json

from harp.controllers.calibration import export_calibration_report, reaggregate_calibration_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("lightgbm", "nn"))
    parser.add_argument("--model", help="HARP artifact path (LightGBM) or run ID (NN)")
    parser.add_argument("--dataset", help="Parquet path (LightGBM) or prepared dataset ID (NN)")
    parser.add_argument("--predictions-report", help="Existing report directory: reaggregate without loading a model")
    parser.add_argument("--output-dir", required=True, help="New report directory")
    parser.add_argument("--split", choices=("train", "validation", "test", "all"))
    parser.add_argument("--target")
    parser.add_argument("--probability", choices=("raw", "platt"))
    parser.add_argument("--n-bins", type=int, default=10)
    parser.add_argument("--strategy", choices=("quantile", "uniform"), default="quantile")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--checkpoint-id")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--input-root", default="pipeline/artifacts/nn_inputs")
    parser.add_argument("--prepared-root", default="pipeline/artifacts/nn_datasets")
    parser.add_argument("--model-root", default="pipeline/artifacts/nn_training")
    parser.add_argument("--odds-snapshot-id")
    parser.add_argument("--odds-root", default="pipeline/artifacts/evaluation_odds")
    parser.add_argument("--odds-market", choices=("win", "place"), default="place")
    parser.add_argument("--place-method", choices=("low", "high", "midpoint", "weighted"), default="midpoint")
    parser.add_argument("--odds-bounds", help="Comma-separated boundaries starting at 1 and ending at inf")
    parser.add_argument("--min-samples-per-bin", type=int, default=30)
    args = vars(parser.parse_args())
    try:
        bounds = args.pop("odds_bounds")
        if bounds is not None:
            args["odds_bounds"] = tuple(float(value) for value in bounds.split(","))
        predictions_report = args.pop("predictions_report")
        if predictions_report:
            if any(args[key] is not None for key in ("backend", "model", "dataset", "split", "target", "probability", "checkpoint_id")):
                raise ValueError("prediction replay cannot change model, dataset, split, target or probabilities")
            for key in ("backend", "model", "dataset", "split", "target", "probability", "checkpoint_id",
                        "device", "batch_size", "input_root", "prepared_root", "model_root"):
                args.pop(key)
            result = reaggregate_calibration_report(predictions_report=predictions_report, **args)
        else:
            if any(args[key] is None for key in ("backend", "model", "dataset")):
                raise ValueError("provide backend, model and dataset, or predictions-report")
            args["split"] = args["split"] or "test"
            args["probability"] = args["probability"] or "raw"
            result = export_calibration_report(**args)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps({"files": result.files, "metrics": result.report.metrics}, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
