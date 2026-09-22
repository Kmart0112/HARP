from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import create_autospec

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from harp.core.inference import OUTPUT_COLUMNS
from harp.core.inference.ev_calculator import PlaceOddsMethod
from harp.core.odds import OddsPolicy, select_odds
from harp.core.race_inputs import RaceInputs
from harp.interface.ports import (
    FileGatewayPort,
    InferenceRepositoryPort,
    ManifestReaderPort,
    ModelLoaderPort,
)
from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort
from harp.usecase.prediction.place import (
    PredictPlaceDeps,
    PredictPlaceRequest,
    run_predict_place_usecase,
)


class _DeterministicModel:
    def predict_proba(self, frame: pd.DataFrame) -> list[list[float]]:
        return [[1.0 - (0.2 + 2 * row[0]), 0.2 + 2 * row[0]] for row in frame]


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
            "num_starters": [2, 2],
            "scheduled_start_at": ["2026-02-24T06:10:00+00:00"] * 2,
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
        "odds_method": PlaceOddsMethod.MIDPOINT,
        "edge_threshold": 0.0,
        "bankroll": 100_000.0,
        "kelly_fraction": 0.1,
        "kelly_cap": 0.05,
        "as_of": datetime(2026, 2, 24, 6, tzinfo=UTC),
        "max_quote_age_seconds": 300,
    }
    values.update(overrides)
    return PredictPlaceRequest(**values)


def _deps(*, model_type: str = "place") -> PredictPlaceDeps:
    repository = create_autospec(InferenceRepositoryPort, instance=True, spec_set=True)
    frame = _features().merge(_race_info(), on=["race_id", "horse_number"])
    quote_frame = _odds().rename(columns={"odds_fukusho_low": "place_low", "odds_fukusho_high": "place_high"})
    quote_frame["win_odds"] = [4.0, 5.0]
    quote_frame["win_popularity"] = [1, 2]
    quote_frame["published_at"] = datetime(2026, 2, 24, 6, tzinfo=UTC)
    quote_frame["available_at"] = None
    policy = OddsPolicy.latest(datetime(2026, 2, 24, 6, tzinfo=UTC), 300)
    repository.load_prediction_input.return_value = RaceInputs(frame, select_odds(frame, quote_frame, policy), "fixture-v1")

    model_loader = create_autospec(ModelLoaderPort, instance=True, spec_set=True)
    model_loader.load_model_payload.return_value = {
        "model": _DeterministicModel(),
        "model_type": model_type,
        "feature_names": ["f1"],
        "cat_features": [],
        "artifact_sha256": "fixture-model-v1",
        "input_contract": {"odds_contract_version": "1.0", "odds_feature_version": "1.0",
                           "feature_names": ["f1"], "training_odds_policy": OddsPolicy.pre_start(max_age_seconds=300).to_dict(),
                           "allowed_prediction_policies": ["latest_before"], "availability_basis": "publication_time",
                           "source_revision": "fixture-v1"},
    }

    manifest_reader = create_autospec(ManifestReaderPort, instance=True, spec_set=True)
    manifest_reader.read_model_type.return_value = model_type
    file_gateway = create_autospec(FileGatewayPort, instance=True, spec_set=True)
    snapshot_store = create_autospec(PredictionSnapshotStorePort, instance=True, spec_set=True)
    snapshot_store.save.return_value = "a" * 64

    return PredictPlaceDeps(
        inference_repository=repository,
        model_loader_port=model_loader,
        manifest_reader_port=manifest_reader,
        file_gateway=file_gateway,
        snapshot_store=snapshot_store,
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


def test_platt_and_ev_use_one_quote_and_keep_missing_rows_visible() -> None:
    deps = _deps(model_type="place_platt")
    payload = deps.model_loader_port.load_model_payload.return_value
    payload["calibration"] = {"method": "platt_logodds", "params": {
        "odds_field": "win_odds", "platt": {"coef": [1.0, 1.0], "intercept": [0.0]}}}
    result = run_predict_place_usecase(_request(), deps)
    assert result.race_entries.p_place.tolist() == pytest.approx([8 / 11, 15 / 17])
    assert result.race_entries.ev_return.tolist() == pytest.approx([76 / 55, 36 / 17])
    assert result.race_entries.quote_id.notna().all()


@pytest.mark.parametrize("missing_market", ["win", "place"])
def test_missing_market_does_not_drop_an_entrant_or_impute_live_odds(missing_market) -> None:
    deps = _deps(model_type="place_platt")
    deps.model_loader_port.load_model_payload.return_value["calibration"] = {
        "method": "platt_logodds", "params": {"platt": {"coef": [1.0, 1.0], "intercept": [0.0]}}}
    inputs = deps.inference_repository.load_prediction_input.return_value
    quotes = inputs.odds.frame
    quotes.loc[0, "win_odds" if missing_market == "win" else "place_low"] = None
    deps.inference_repository.load_prediction_input.return_value = RaceInputs(
        inputs.frame, select_odds(inputs.frame, quotes, inputs.odds.policy), "missing-market")
    result = run_predict_place_usecase(_request(), deps)
    assert len(result.race_entries) == 2
    assert pd.isna(result.race_entries.iloc[0].ev_return)
    assert 1 not in result.edge_candidates.horse_number.tolist()
    if missing_market == "win":
        assert pd.isna(result.race_entries.iloc[0].p_place)
        assert result.race_entries.iloc[0].prediction_status == "missing_calibration_odds"
        assert result.shifted_race_entries.prediction_status.eq("incomplete_race").all()
    else:
        assert result.race_entries.iloc[0].p_place == pytest.approx(8 / 11)


def test_replay_uses_saved_input_when_database_is_unavailable(tmp_path):
    from dataclasses import replace

    from harp.adapters.driven.storage.prediction_snapshot_store import (
        ParquetPredictionSnapshotStore,
    )
    deps = replace(_deps(), snapshot_store=ParquetPredictionSnapshotStore(tmp_path))
    original = run_predict_place_usecase(_request(), deps)
    deps.inference_repository.load_prediction_input.side_effect = RuntimeError("database disconnected")
    replay = run_predict_place_usecase(_request(replay_snapshot_id=original.input_snapshot_id), deps)
    assert_frame_equal(original.race_entries, replay.race_entries)
    assert_frame_equal(original.edge_candidates, replay.edge_candidates)
    assert original.input_snapshot_id == replay.input_snapshot_id


@pytest.mark.parametrize("change", ["model", "odds_method", "bankroll", "cutoff"])
def test_replay_rejects_changed_model_or_decision_parameters(tmp_path, change):
    from dataclasses import replace

    from harp.adapters.driven.storage.prediction_snapshot_store import (
        ParquetPredictionSnapshotStore,
    )
    from harp.core.odds import OddsContractError
    deps = replace(_deps(), snapshot_store=ParquetPredictionSnapshotStore(tmp_path))
    original = run_predict_place_usecase(_request(), deps)
    params = {"replay_snapshot_id": original.input_snapshot_id}
    if change == "model":
        deps.model_loader_port.load_model_payload.return_value["artifact_sha256"] = "different-model"
    elif change == "odds_method":
        params["odds_method"] = PlaceOddsMethod.LOW
    elif change == "bankroll":
        params["bankroll"] = 200_000
    else:
        params["as_of"] = datetime(2026, 2, 24, 6, 1, tzinfo=UTC)
    with pytest.raises(OddsContractError, match="replay model or input request"):
        run_predict_place_usecase(_request(**params), deps)


@pytest.mark.parametrize("change", ["legacy", "version", "features", "policy"])
def test_model_input_contract_prevents_silent_semantic_migration(change):
    from harp.core.odds import OddsContractError
    deps = _deps()
    payload = deps.model_loader_port.load_model_payload.return_value
    if change == "legacy":
        del payload["input_contract"]
    elif change == "version":
        payload["input_contract"]["odds_feature_version"] = "unknown"
    elif change == "features":
        payload["input_contract"]["feature_names"] = ["other"]
    else:
        payload["input_contract"]["allowed_prediction_policies"] = []
    with pytest.raises(OddsContractError):
        run_predict_place_usecase(_request(), deps)


def test_prediction_cannot_publish_success_when_input_persistence_fails():
    deps = _deps()
    deps.snapshot_store.save.side_effect = OSError("disk full")
    with pytest.raises(OSError, match="disk full"):
        run_predict_place_usecase(_request(), deps)


def test_closed_races_have_no_prediction_or_betting_candidates():
    deps = _deps()
    inputs = deps.inference_repository.load_prediction_input.return_value
    rows = inputs.frame.copy()
    rows["scheduled_start_at"] = "2026-02-24T06:00:00+00:00"
    deps.inference_repository.load_prediction_input.return_value = RaceInputs(rows, inputs.odds, "closed")
    result = run_predict_place_usecase(_request(), deps)
    assert result.race_entries.prediction_status.eq("race_closed").all()
    assert result.race_entries.p_place.isna().all()
    assert result.edge_candidates.empty
