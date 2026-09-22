from datetime import UTC, datetime

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from harp.adapters.driven.storage.prediction_snapshot_store import (
    ParquetPredictionSnapshotStore,
)
from harp.core.odds import OddsContractError, OddsPolicy, select_odds
from harp.core.race_inputs import RaceInputs
from harp.interface.ports.prediction_snapshot_ports import PredictionSnapshotStorePort


def sample_inputs():
    as_of = datetime(2026, 6, 13, 6, tzinfo=UTC)
    rows = pd.DataFrame({"race_id": ["R1"], "horse_number": [1], "speed": [0.4]})
    quotes = rows.assign(win_odds=4., place_low=1.8, place_high=2., win_popularity=1,
                         published_at=as_of, available_at=None)
    return RaceInputs(rows, select_odds(rows, quotes, OddsPolicy.latest(as_of, 300)), "sample")


def test_snapshot_port_round_trips_input_without_reading_current_database(tmp_path):
    port: PredictionSnapshotStorePort = ParquetPredictionSnapshotStore(tmp_path)
    original = sample_inputs()
    reference = port.save(original, {"model_id": "model-a"})
    exposed_frame = original.frame
    exposed_frame.loc[0, "speed"] = 999
    assert original.frame.speed.tolist() == [0.4]
    loaded = port.load(reference)
    assert loaded.metadata == {"model_id": "model-a"}
    assert loaded.inputs.frame.speed.tolist() == [0.4]
    assert_frame_equal(loaded.inputs.odds.frame, sample_inputs().odds.frame)
    assert port.save(loaded.inputs, loaded.metadata) == reference
    assert not list(tmp_path.glob(".pending-*"))


def test_snapshot_port_detects_corrupted_input_before_returning_data(tmp_path):
    port: PredictionSnapshotStorePort = ParquetPredictionSnapshotStore(tmp_path)
    reference = port.save(sample_inputs(), {})
    (tmp_path / reference / "odds.parquet").write_bytes(b"changed after publication")
    with pytest.raises(OddsContractError, match="integrity"):
        port.load(reference)
