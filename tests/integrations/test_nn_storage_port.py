import json

from pandas.testing import assert_frame_equal
import pytest

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore, ParquetNnPredictionSnapshotStore
from harp.adapters.driven.storage.nn_feature_contract import JsonNnFeatureContractReader
from harp.core.nn.contracts import NnInputContractError
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort, NnPredictionSnapshotPort
from tests.nn_input_support import training_inputs


def test_saved_dataset_round_trips_features_history_and_nullable_targets(tmp_path):
    port: NnDatasetStorePort = ParquetNnDatasetStore(tmp_path)
    original = training_inputs()
    identity = port.save(original, {"purpose": "training", "split": {"validation_year": 2026}})
    entries, history, targets = original.inputs.entries, original.inputs.history, original.targets
    entries.loc[0, "age"] = 99
    history.loc[0, "result_order"] = 99
    targets.loc[0, "is_place"] = False
    loaded = port.load(identity)
    assert_frame_equal(loaded.inputs.inputs.entries, training_inputs().inputs.entries)
    assert_frame_equal(loaded.inputs.inputs.history, training_inputs().inputs.history)
    assert_frame_equal(loaded.inputs.targets, training_inputs().targets)
    assert loaded.inputs.inputs.query == original.inputs.query
    assert loaded.inputs.inputs.contract == original.inputs.contract
    assert loaded.inputs.inputs.captured_at == original.inputs.captured_at
    assert loaded.metadata == {"purpose": "training", "split": {"validation_year": 2026}}
    assert port.save(loaded.inputs, loaded.metadata) == identity
    assert not list(tmp_path.glob(".pending-*"))


def test_prediction_snapshot_has_no_current_targets_and_cannot_load_as_training(tmp_path):
    port: NnPredictionSnapshotPort = ParquetNnPredictionSnapshotStore(tmp_path)
    identity = port.save(training_inputs().inputs, {"model_id": "nn-v1"})
    loaded = port.load(identity)
    assert_frame_equal(loaded.inputs.history, training_inputs().inputs.history)
    assert loaded.metadata == {"model_id": "nn-v1"}
    assert not (tmp_path / identity / "targets.parquet").exists()
    with pytest.raises(NnInputContractError, match="kind"):
        ParquetNnDatasetStore(tmp_path).load(identity)


@pytest.mark.parametrize("filename", ["entries.parquet", "history.parquet", "targets.parquet", "manifest.json"])
def test_store_detects_corruption_before_returning_inputs(tmp_path, filename):
    port: NnDatasetStorePort = ParquetNnDatasetStore(tmp_path)
    identity = port.save(training_inputs(), {})
    (tmp_path / identity / filename).write_bytes(b"corrupted")
    with pytest.raises(NnInputContractError, match="integrity"):
        port.load(identity)


def test_unserializable_metadata_does_not_publish_a_partial_dataset(tmp_path):
    port: NnDatasetStorePort = ParquetNnDatasetStore(tmp_path)
    with pytest.raises(ValueError):
        port.save(training_inputs(), {"invalid": float("nan")})
    assert list(tmp_path.iterdir()) == []


def test_feature_contract_reader_preserves_order_and_rejects_current_outcomes(tmp_path):
    path = tmp_path / "contract.json"
    contract = {"version": 1, "pre_race": [{"name": "age", "kind": "numeric"}],
                "history_results": [{"name": "result_order", "kind": "numeric"}]}
    path.write_text(json.dumps(contract))
    reader = JsonNnFeatureContractReader()
    assert reader.load(str(path)).pre_race_names == ("age",)
    assert reader.load(str(path)).history_result_names == ("result_order",)
    contract["pre_race"] = [{"name": "is_place", "kind": "numeric"}]
    path.write_text(json.dumps(contract))
    with pytest.raises(NnInputContractError):
        reader.load(str(path))
