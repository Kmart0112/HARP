from unittest.mock import create_autospec

import pytest

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.split import NnDatasetConfig
from harp.interface.ports.nn_input_ports import NnInputRepositoryPort
from harp.interface.ports.nn_prepared_dataset_ports import NnPreparedDatasetStorePort
from harp.interface.ports.nn_storage_ports import NnDatasetStorePort, StoredNnDataset
from harp.usecase.nn_dataset.dto import NnDatasetDeps, PrepareNnDatasetRequest
from harp.usecase.nn_dataset.prepare import load_prepared_nn_dataset, run_prepare_nn_dataset_usecase
from tests.nn_dataset_support import dataset_inputs


def dataset_deps(inputs):
    raw, recipes = {}, {}
    input_store = create_autospec(NnDatasetStorePort, instance=True, spec_set=True)
    prepared_store = create_autospec(NnPreparedDatasetStorePort, instance=True, spec_set=True)
    repository = create_autospec(NnInputRepositoryPort, instance=True, spec_set=True)
    repository.load_training_inputs.return_value = inputs

    def save_input(value, metadata):
        raw["a" * 64] = StoredNnDataset(value, metadata)
        return "a" * 64

    def save_prepared(recipe):
        recipes["b" * 64] = recipe
        return "b" * 64

    input_store.save.side_effect = save_input
    input_store.load.side_effect = raw.__getitem__
    prepared_store.save.side_effect = save_prepared
    prepared_store.load.side_effect = recipes.__getitem__
    return NnDatasetDeps(input_store, prepared_store, repository), raw, recipes


def test_prepare_from_repository_publishes_replayable_recipe_with_source_identity():
    inputs = dataset_inputs()
    deps, raw, recipes = dataset_deps(inputs)
    result = run_prepare_nn_dataset_usecase(
        PrepareNnDatasetRequest(NnDatasetConfig("2026-06-13", "2026-06-20", 2), query=inputs.inputs.query), deps,
    )
    assert raw[result.input_dataset_id].inputs.inputs.entries.race_id.nunique() == 3
    assert recipes[result.prepared_dataset_id].input_dataset_id == result.input_dataset_id
    assert result.summary["train"]["entries"] == 2
    deps.repository.load_training_inputs.side_effect = AssertionError("replay must not query the DB")
    replayed = load_prepared_nn_dataset(result.prepared_dataset_id, deps)
    assert replayed.split("train")[0]["horse_ids"] == ("H1", "H2")
    assert replayed.summary == result.summary


def test_saved_input_preparation_reuses_identity_and_needs_no_repository():
    inputs = dataset_inputs()
    deps, raw, recipes = dataset_deps(inputs)
    raw["c" * 64] = StoredNnDataset(inputs, {})
    deps = NnDatasetDeps(deps.input_store, deps.prepared_store)
    result = run_prepare_nn_dataset_usecase(
        PrepareNnDatasetRequest(NnDatasetConfig("2026-06-13", "2026-06-20", 1), input_dataset_id="c" * 64), deps,
    )
    assert set(raw) == {"c" * 64}
    assert result.input_dataset_id == "c" * 64
    assert recipes[result.prepared_dataset_id].config.history_length == 1


def test_unusable_training_split_does_not_publish_inputs_or_prepared_artifact():
    inputs = dataset_inputs(unknown_train_label=True)
    deps, raw, recipes = dataset_deps(inputs)
    with pytest.raises(NnInputContractError, match="no fully labelled races"):
        run_prepare_nn_dataset_usecase(
            PrepareNnDatasetRequest(NnDatasetConfig("2026-06-13", "2026-06-20", 2), query=inputs.inputs.query), deps,
        )
    assert not raw
    assert not recipes


def test_recipe_publication_failure_does_not_report_a_completed_dataset():
    inputs = dataset_inputs()
    deps, raw, recipes = dataset_deps(inputs)
    deps.prepared_store.save.side_effect = OSError("storage full")
    with pytest.raises(OSError, match="storage full"):
        run_prepare_nn_dataset_usecase(
            PrepareNnDatasetRequest(NnDatasetConfig("2026-06-13", "2026-06-20", 2), query=inputs.inputs.query), deps,
        )
    # The immutable source may already be published and can be reused on retry.
    assert len(raw) == 1
    assert not recipes
