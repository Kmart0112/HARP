from __future__ import annotations

from typing import Any
from unittest.mock import create_autospec

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from harp.core.inference import OUTPUT_COLUMNS
from harp.interface.ports import (
    FileGatewayPort,
    InferenceRepositoryPort,
    ManifestReaderPort,
    ModelLoaderPort,
)
from harp.usecase.prediction.place import (
    PredictPlaceDeps,
    PredictPlaceRequest,
    run_predict_place_usecase,
)


class _DeterministicModel:
    def predict_proba(self, frame: pd.DataFrame) -> list[list[float]]:
        probabilities = [0.4, 0.6]
        return [[1.0 - probability, probability] for probability in probabilities[: len(frame)]]


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "race_id": ["R1", "R1"],
            "horse_number": [1, 2],
            "held_date": ["2026-02-24", "2026-02-24"],
            "surface": ["turf", "turf"],
            "distance_m": [1600, 1600],
            "horse_name": ["A", "B"],
            "f1": [0.1, 0.2],
        }
    )


def _odds() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "race_id": ["R1", "R1"],
            "horse_number": [1, 2],
            "odds_fukusho_low": [1.8, 2.2],
            "odds_fukusho_high": [2.0, 2.6],
            "odds_fukusho_avg": [1.9, 2.4],
            "odds_fukusho_weighted_avg": [1.86, 2.32],
        }
    )


def _race_info() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "race_id": ["R1", "R1"],
            "horse_number": [1, 2],
            "jyo_name": ["Tokyo", "Tokyo"],
            "round": [11, 11],
            "popularity": [1, 2],
        }
    )


def _request(**overrides: Any) -> PredictPlaceRequest:
    values: dict[str, Any] = {
        "artifact_path": "artifacts/place.pkl",
        "manifest_path": None,
        "from_date": "2026-02-24",
        "to_date": "2026-02-24",
        "limit": None,
        "fukusho_type": "odds_fukusho_avg",
        "edge_threshold": 0.0,
        "bankroll": 100_000.0,
        "kelly_fraction": 0.1,
        "kelly_cap": 0.05,
    }
    values.update(overrides)
    return PredictPlaceRequest(**values)


def _deps(*, model_type: str = "place") -> PredictPlaceDeps:
    repository = create_autospec(InferenceRepositoryPort, instance=True, spec_set=True)
    repository.load_recent_features.return_value = _features()
    repository.load_odds.return_value = _odds()
    repository.load_race_info.return_value = _race_info()

    model_loader = create_autospec(ModelLoaderPort, instance=True, spec_set=True)
    model_loader.load_model_payload.return_value = {
        "model": _DeterministicModel(),
        "model_type": model_type,
        "feature_names": ["f1"],
        "cat_features": [],
    }

    manifest_reader = create_autospec(ManifestReaderPort, instance=True, spec_set=True)
    manifest_reader.read_model_type.return_value = model_type
    file_gateway = create_autospec(FileGatewayPort, instance=True, spec_set=True)

    return PredictPlaceDeps(
        inference_repository=repository,
        model_loader_port=model_loader,
        manifest_reader_port=manifest_reader,
        file_gateway=file_gateway,
        mart_table="mart.predict_features",
    )


def test_prediction_flow_returns_ranked_entries_and_edge_candidates() -> None:
    result = run_predict_place_usecase(_request(edge_threshold=0.25), _deps())

    assert result.from_date == "2026-02-24"
    assert result.to_date == "2026-02-24"
    assert list(result.race_entries.columns) == OUTPUT_COLUMNS
    assert result.race_entries["horse_number"].tolist() == [1, 2]
    assert result.race_entries["p_place"].tolist() == pytest.approx([0.4, 0.6])
    assert result.edge_candidates["horse_number"].tolist() == [2]
    assert result.edge_candidates["edge"].tolist() == pytest.approx([0.2666666667])
    assert result.shifted_race_entries is None
    assert result.shifted_edge_candidates is None


def test_prediction_flow_rejects_non_place_model_without_partial_output() -> None:
    with pytest.raises(ValueError, match="supports place models only"):
        run_predict_place_usecase(_request(), _deps(model_type="win"))


def test_prediction_flow_is_deterministic_for_the_same_boundary_inputs() -> None:
    first = run_predict_place_usecase(_request(), _deps())
    second = run_predict_place_usecase(_request(), _deps())

    assert_frame_equal(first.race_entries, second.race_entries)
    assert_frame_equal(first.edge_candidates, second.edge_candidates)
