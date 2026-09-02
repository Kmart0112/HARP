from __future__ import annotations

from harp.controllers import TrainPipelineKind
from pipeline.jobs._train_job_common import TrainJobSpec, run_training_job


SPEC = TrainJobSpec(
    job_name="run_tansho_train",
    description="Train win model and output artifact/manifest.",
    pipeline_kind=TrainPipelineKind.WIN,
    train_year_start=2017,
    train_year_end=2025,
    test_year=2025,
    feature_set_example="win_v1",
    artifact_out="pipeline/artifacts/models/is_win_v1.pkl",
    manifest_out="pipeline/artifacts/metadata/is_win_v1.json",
    legacy_artifact_out="models/is_win_v1.pkl",
)


def main() -> None:
    run_training_job(SPEC)


if __name__ == "__main__":
    main()
