import json

from pandas.testing import assert_frame_equal
import pytest

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore, ParquetNnPredictionSnapshotStore
from harp.adapters.driven.storage.nn_feature_contract import JsonNnFeatureContractReader
from harp.core.nn.contracts import NnInputContractError
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort, NnPredictionSnapshotPort
from tests.nn_input_support import training_inputs
from tests.nn_opponent_support import opponent_inputs


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


def test_opponent_dataset_round_trip_preserves_contract_and_db_free_preparation(tmp_path):
    from harp.core.nn.dataset import prepare_nn_dataset, restore_nn_dataset
    from harp.core.nn.split import NnDatasetConfig
    import numpy as np

    store = ParquetNnDatasetStore(tmp_path)
    source = opponent_inputs()
    identity = store.save(source, {"purpose": "opponent-context"})
    restored = store.load(identity).inputs
    assert restored.inputs.contract == source.inputs.contract
    assert restored.inputs.query == source.inputs.query
    assert_frame_equal(restored.inputs.history, source.inputs.history)
    prepared = prepare_nn_dataset(source, NnDatasetConfig("2026-06-13", "2026-06-20", 3))
    replayed = restore_nn_dataset(restored, prepared.config, prepared.preprocessing, prepared.partitions)
    for index in range(len(prepared.dataset)):
        np.testing.assert_array_equal(prepared.dataset[index]["history_numeric"], replayed.dataset[index]["history_numeric"])


def test_legacy_snapshot_without_context_still_restores_and_can_be_saved_again(tmp_path):
    from dataclasses import asdict
    from hashlib import sha256

    source = training_inputs()
    base = source.inputs
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    files = {}
    for name, frame in (("entries.parquet", base.entries), ("history.parquet", base.history),
                        ("targets.parquet", source.targets)):
        frame.to_parquet(legacy / name, index=False)
        files[name] = {"sha256": sha256((legacy / name).read_bytes()).hexdigest(), "rows": len(frame)}
    query = asdict(base.query)
    query.pop("history_context_names")
    contract = asdict(base.contract)
    contract.pop("history_context")
    contract["version"] = 1
    manifest = {"version": 1, "kind": "training", "availability_basis": "event_date",
                "query": query, "feature_contract": contract,
                "source_revision": base.source_revision, "captured_at": base.captured_at.isoformat(),
                "metadata": {}, "files": files}
    encoded = json.dumps(manifest, sort_keys=True).encode()
    identity = sha256(encoded).hexdigest()
    (legacy / "manifest.json").write_bytes(encoded)
    legacy.rename(tmp_path / identity)
    store = ParquetNnDatasetStore(tmp_path)
    restored = store.load(identity).inputs
    assert restored.inputs.contract.version == 1
    assert restored.inputs.query.history_context_names == ()
    assert_frame_equal(restored.inputs.history, base.history)
    resaved = store.load(store.save(restored, {})).inputs
    assert_frame_equal(resaved.inputs.history, base.history)


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
