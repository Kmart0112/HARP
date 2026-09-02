from __future__ import annotations

import argparse

from harp.controllers import FeatureSetRenderController, RenderFeatureSetCommand
from pipeline.runtime_settings import load_pipeline_runtime_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a named feature set from the centralized feature registry.",
    )
    parser.add_argument("--feature-set", required=True, help="Named feature set in the registry.")
    parser.add_argument(
        "--mode",
        default="production",
        choices=["production", "validation"],
        help="Registry selection mode.",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Override feature registry path. Defaults to HARP feature registry setting.",
    )
    parser.add_argument("--out", default=None, help="Optional output file path.")
    parser.add_argument("--stdout", action="store_true", help="Print rendered YAML to stdout.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_pipeline_runtime_config()
    result = FeatureSetRenderController(config).run(
        RenderFeatureSetCommand(
            feature_set_name=args.feature_set,
            mode=args.mode,
            registry_path=args.registry,
            output_path=args.out,
        )
    )

    if args.stdout or not args.out:
        print(
            result.rendered_text,
            end="" if result.rendered_text.endswith("\n") else "\n",
        )


if __name__ == "__main__":
    main()
