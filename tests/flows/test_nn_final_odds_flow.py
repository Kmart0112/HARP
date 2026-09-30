from dataclasses import replace
from types import SimpleNamespace

import pytest

from harp.core.nn.dataset import prepare_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetRecipe
from harp.interface.ports.nn_storage_ports import StoredNnDataset
from harp.usecase.nn_dataset.odds import (
    CaptureNnFinalOddsDeps,
    CaptureNnFinalOddsRequest,
    run_capture_nn_final_odds_usecase,
)
from tests.nn_dataset_support import dataset_inputs
from tests.nn_odds_support import batch, quotes


class MemorySnapshots:
    def __init__(self):
        self.values = {}

    def save(self, value):
        self.values["c" * 64] = value
        return "c" * 64


def deps(*, all_missing=False):
    inputs = dataset_inputs()
    prepared = prepare_nn_dataset(inputs, NnDatasetConfig("2026-06-13", "2026-06-20", 2))
    parts = tuple(replace(part, exclusion_reason="excluded_fixture") if part.split == "validation" else part
                  for part in prepared.partitions)
    recipe = NnPreparedDatasetRecipe("b" * 64, prepared.config, prepared.preprocessing, parts)
    store = MemorySnapshots()

    def load(query):
        frame = quotes(query.keys)
        if all_missing:
            frame["place_low"] = None
        return batch(frame.iloc[::-1])

    dependencies = CaptureNnFinalOddsDeps(
        SimpleNamespace(load=lambda identity: StoredNnDataset(inputs, {})),
        SimpleNamespace(load=lambda identity: recipe), SimpleNamespace(load=load), store)
    return dependencies, store


def test_capture_keeps_saved_splits_and_horse_identity_without_readmitting_excluded_races():
    dependencies, store = deps()
    result = run_capture_nn_final_odds_usecase(CaptureNnFinalOddsRequest("a" * 64), dependencies)
    assert result.entries == 3 and result.races == 2
    assert result.statuses == {"available": 3}
    frame = store.values[result.snapshot_id].frame
    assert frame.race_id.tolist() == ["R2", "R2", "R4"]
    assert frame.kettonum.tolist() == ["H1", "H2", "H3"]
    assert frame.split.tolist() == ["train", "train", "test"]
    assert result.input_dataset_id == "b" * 64


def test_capture_with_no_train_teachers_does_not_publish_a_snapshot():
    dependencies, store = deps(all_missing=True)
    with pytest.raises(ValueError, match="no available"):
        run_capture_nn_final_odds_usecase(CaptureNnFinalOddsRequest("a" * 64), dependencies)
    assert not store.values


def test_repository_failure_does_not_publish_partial_teachers():
    dependencies, store = deps()

    def fail(query):
        raise RuntimeError("database unavailable")

    dependencies = replace(dependencies, repository=SimpleNamespace(load=fail))
    with pytest.raises(RuntimeError, match="database unavailable"):
        run_capture_nn_final_odds_usecase(CaptureNnFinalOddsRequest("a" * 64), dependencies)
    assert not store.values
