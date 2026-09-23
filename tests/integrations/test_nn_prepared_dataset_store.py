import numpy as np
import pytest

from harp.adapters.driven.storage.nn_dataset_store import ParquetNnDatasetStore
from harp.adapters.driven.storage.nn_prepared_dataset_store import JsonNnPreparedDatasetStore
from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import collate_nn_races
from harp.core.nn.split import NnDatasetConfig
from harp.usecase.nn_dataset.dto import NnDatasetDeps, PrepareNnDatasetRequest
from harp.usecase.nn_dataset.prepare import load_prepared_nn_dataset, run_prepare_nn_dataset_usecase
from tests.nn_dataset_support import dataset_inputs


def stored_dataset(root):
    deps = NnDatasetDeps(ParquetNnDatasetStore(root / "inputs"), JsonNnPreparedDatasetStore(root / "prepared"))
    input_id = deps.input_store.save(dataset_inputs(), {"source": "integration"})
    req = PrepareNnDatasetRequest(NnDatasetConfig("2026-06-13", "2026-06-20", 3), input_dataset_id=input_id)
    result = run_prepare_nn_dataset_usecase(req, deps)
    return deps, req, result


def test_dataset_roundtrip_preserves_batches_splits_and_feature_dictionaries_without_db(tmp_path):
    deps, req, result = stored_dataset(tmp_path)
    recipe = deps.prepared_store.load(result.prepared_dataset_id)
    assert recipe.input_dataset_id == result.input_dataset_id
    assert len(recipe.partitions) == 3
    assert recipe.preprocessing.current.categorical[0].values == ("1",)
    first = load_prepared_nn_dataset(result.prepared_dataset_id, deps)
    fresh_deps = NnDatasetDeps(ParquetNnDatasetStore(tmp_path / "inputs"), JsonNnPreparedDatasetStore(tmp_path / "prepared"))
    replay = load_prepared_nn_dataset(result.prepared_dataset_id, fresh_deps)
    assert replay.summary == result.summary
    assert replay.preprocessing == first.preprocessing
    expected = collate_nn_races([first.dataset[index] for index in range(3)])
    actual = collate_nn_races([replay.dataset[index] for index in range(3)])
    for key in expected:
        if isinstance(expected[key], np.ndarray):
            np.testing.assert_array_equal(actual[key], expected[key])
        else:
            assert actual[key] == expected[key]
    # Repeated publication of the same preparation yields the same identity.
    assert run_prepare_nn_dataset_usecase(req, deps).prepared_dataset_id == result.prepared_dataset_id
    assert not list((tmp_path / "prepared").glob(".pending-*"))


@pytest.mark.parametrize("corrupted", ["recipe", "source_history", "missing_source"])
def test_replay_rejects_corrupt_or_missing_recipe_dependencies(tmp_path, corrupted):
    deps, _, result = stored_dataset(tmp_path)
    if corrupted == "recipe":
        path = tmp_path / "prepared" / result.prepared_dataset_id / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        path = tmp_path / "inputs" / result.input_dataset_id / "history.parquet"
        if corrupted == "missing_source":
            path.unlink()
        else:
            path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(NnInputContractError):
        load_prepared_nn_dataset(result.prepared_dataset_id, deps)
