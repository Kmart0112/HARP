from __future__ import annotations

from harp.controllers import TrainPipelineKind
from pipeline.jobs._train_job_common import TrainJobSpec, run_training_job


SPEC = TrainJobSpec(
    job_name="run_train",
    description="Train place model and output artifact/manifest.",
    pipeline_kind=TrainPipelineKind.PLACE,
    train_year_start=2015,
    train_year_end=2025,
    test_year=2026,
    feature_set_example="place_rank_v1",
    artifact_out="pipeline/artifacts/models/is_place_v1.pkl",
    manifest_out="pipeline/artifacts/metadata/is_place_v1.json",
    legacy_artifact_out="models/is_place_v1.pkl",
)


def main() -> None:
    run_training_job(SPEC)


if __name__ == "__main__":
    main()
