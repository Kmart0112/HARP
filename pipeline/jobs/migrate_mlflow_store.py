from __future__ import annotations

import argparse
from harp.controllers import MlflowStoreMigrationController, MlflowStoreMigrationCommand
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate local MLflow store metadata and artifacts.")
    parser.add_argument("--source-store-dir", type=str, default=None)
    parser.add_argument("--target-tracking-uri", type=str, default=None)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()
    result = MlflowStoreMigrationController(config).run(
        MlflowStoreMigrationCommand(
            source_store_dir=args.source_store_dir,
            target_tracking_uri=args.target_tracking_uri,
            check=bool(args.check),
        ),
    )
    print(f"check_only={result.check_only}")
    print(f"source_store={result.source_store_dir}")
    print(f"target_store={result.target_store_dir}")
    print(f"copied_files={len(result.copied_files)}")
    print(f"rewritten_meta_files={len(result.rewritten_meta_files)}")
    print(f"verified_experiments={','.join(result.verified_experiment_names)}")


if __name__ == "__main__":
    main()
