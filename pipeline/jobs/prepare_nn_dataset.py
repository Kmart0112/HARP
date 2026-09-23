"""Create replayable NN race Datasets from dbt inputs or an input snapshot."""
import argparse
from dataclasses import asdict
import json

from harp.controllers.nn_dataset.controller import NnDatasetController, PrepareNnDatasetCommand
from pipeline.runtime_settings import load_pipeline_env_files, resolve_database_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-dataset-id", help="Replay a saved input snapshot without DB access")
    source.add_argument("--from-date", help="First target event date, inclusive")
    parser.add_argument("--to-date", help="Last target event date, inclusive (DB mode)")
    parser.add_argument("--train-end-date", required=True, help="Inclusive train end date")
    parser.add_argument("--validation-end-date", required=True, help="Inclusive validation end; later targets become test")
    parser.add_argument("--history-length", type=int, default=10)
    parser.add_argument("--max-races", type=int, help="Take earliest complete races in DB mode; primarily for smoke checks")
    parser.add_argument("--input-root", default="pipeline/artifacts/nn_inputs")
    parser.add_argument("--prepared-root", default="pipeline/artifacts/nn_datasets")
    parser.add_argument("--contract-path", default="pipeline/config/nn_input_contract.json")
    args = parser.parse_args()
    if args.from_date and not args.to_date:
        parser.error("--from-date requires --to-date")
    if args.input_dataset_id and (args.to_date or args.max_races is not None):
        parser.error("saved input mode cannot use --to-date or --max-races")
    try:
        db_url = None
        if args.from_date:
            load_pipeline_env_files()
            db_url = resolve_database_url()
        result = NnDatasetController(args.input_root, args.prepared_root, db_url=db_url).run(
            PrepareNnDatasetCommand(
                train_end_date=args.train_end_date, validation_end_date=args.validation_end_date,
                history_length=args.history_length, input_dataset_id=args.input_dataset_id,
                from_date=args.from_date, to_date=args.to_date, max_races=args.max_races,
                contract_path=args.contract_path,
            )
        )
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
