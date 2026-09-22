from __future__ import annotations

from unittest.mock import create_autospec

import pandas as pd

from harp.core.feature_definitions import FeatureSetDefinition
from harp.core.odds import OddsPolicy, select_odds
from harp.core.race_inputs import RaceInputs
from harp.interface.ports import (
    ArtifactStorePort,
    FeatureDefinitionPort,
    FileGatewayPort,
    ManifestStorePort,
    TrainingRepositoryPort,
)
from harp.usecase.explanation.artifact_dataset import (
    ArtifactExplanationDatasetDeps,
    ArtifactExplanationDatasetRequest,
    run_rebuild_artifact_explanation_dataset_usecase,
)
from harp.usecase.feature_registry.render import (
    RenderFeatureSetDeps,
    RenderFeatureSetRequest,
    run_render_feature_set_usecase,
)
from harp.usecase.notebook_artifact.model_artifact import (
    NotebookModelArtifactSaveDeps,
    NotebookModelArtifactSaveRequest,
    run_export_notebook_model_artifact_usecase,
)


def test_artifact_explanation_flow_rebuilds_the_original_year_splits_from_mocked_data() -> None:
    repository = create_autospec(TrainingRepositoryPort, instance=True, spec_set=True)
    frame = pd.DataFrame(
        {
            "held_year": [2018, 2018, 2019, 2020],
            "speed": [1.0, 2.0, 3.0, 4.0],
            "is_place": [0, 1, 0, 1],
        }
    )
    frame["race_id"] = ["A", "B", "C", "D"]
    frame["horse_number"] = 1
    frame["held_date"] = frame.held_year.astype(str) + "-06-01"
    frame["scheduled_start_at"] = frame.held_date + "T06:10:00+00:00"
    quotes = frame[["race_id", "horse_number"]].copy()
    for column in ["win_odds", "place_low", "place_high", "win_popularity", "published_at", "available_at"]:
        quotes[column] = None
    policy = OddsPolicy.pre_start(max_age_seconds=300)
    repository.load_training_input.return_value = RaceInputs(frame, select_odds(frame, quotes, policy), "fixture")
    payload = {
        "input_contract": {"odds_contract_version": "1.0", "odds_feature_version": "1.0",
                           "feature_names": ["speed"], "training_odds_policy": policy.to_dict(),
                           "allowed_prediction_policies": []},
        "feature_names": ["speed"],
        "cat_features": [],
        "split_info": {
            "train_year_start": 2018,
            "train_year_end": 2019,
            "test_year": 2020,
        },
    }

    result = run_rebuild_artifact_explanation_dataset_usecase(
        ArtifactExplanationDatasetRequest(payload=payload, target_col="is_place"),
        ArtifactExplanationDatasetDeps(
            training_repository=repository,
        ),
    )

    assert len(result.ds.X_tr) == 2
    assert len(result.ds.X_val) == 1
    assert len(result.ds.X_test) == 1
    assert result.ds.feature_names == ["speed"]


def test_notebook_artifact_flow_persists_payload_and_matching_manifest() -> None:
    artifact_store = create_autospec(ArtifactStorePort, instance=True, spec_set=True)
    manifest_store = create_autospec(ManifestStorePort, instance=True, spec_set=True)
    manifest_store.build_manifest.return_value = {
        "model_type": "place",
        "artifact_path": "artifacts/place.pkl",
    }
    request = NotebookModelArtifactSaveRequest(
        payload={"model_type": "place", "feature_names": ["speed"]},
        model_type="place",
        artifact_out="artifacts/place.pkl",
        manifest_out="artifacts/place.json",
        feature_names=["speed"],
        cat_features=[],
        train_year_start=2018,
        train_year_end=2019,
        test_year=2020,
        metrics={"auc": 0.72},
        source_table="mart.train_features",
        note="notebook export",
    )

    result = run_export_notebook_model_artifact_usecase(
        request,
        NotebookModelArtifactSaveDeps(
            artifact_store_port=artifact_store,
            manifest_store_port=manifest_store,
        ),
    )

    assert result.artifact_out == "artifacts/place.pkl"
    assert result.manifest_out == "artifacts/place.json"
    artifact_store.save_artifact.assert_called_once_with(request.payload, request.artifact_out)
    manifest_store.write_manifest.assert_called_once_with(
        manifest_store.build_manifest.return_value,
        request.manifest_out,
    )


def test_feature_registry_flow_renders_the_resolved_set_to_the_requested_output() -> None:
    definitions = create_autospec(FeatureDefinitionPort, instance=True, spec_set=True)
    definitions.load_feature_set.return_value = FeatureSetDefinition(
        name="place_v1",
        feature_names=("speed", "course"),
        cat_features=("course",),
    )
    definitions.render_feature_config.return_value = (
        "feature_names: [speed, course]\ncat_features: [course]\n"
    )
    files = create_autospec(FileGatewayPort, instance=True, spec_set=True)

    result = run_render_feature_set_usecase(
        RenderFeatureSetRequest(
            registry_path="registry.yml",
            feature_set_name="place_v1",
            mode="production",
            output_path="outputs/features.yml",
        ),
        RenderFeatureSetDeps(file_gateway=files, feature_definition_port=definitions),
    )

    assert result.feature_names == ("speed", "course")
    assert result.cat_features == ("course",)
    assert result.rendered_text == "feature_names: [speed, course]\ncat_features: [course]\n"
    files.write_text.assert_called_once_with("outputs/features.yml", result.rendered_text)
