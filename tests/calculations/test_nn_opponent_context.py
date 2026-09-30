from dataclasses import replace

import numpy as np
import pytest

from harp.core.nn.contracts import NnFeatureField, NnInputContractError, NnRaceInputs
from harp.core.nn.dataset import collate_nn_races, prepare_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from tests.nn_dataset_support import dataset_inputs, replace_inputs
from tests.nn_opponent_support import opponent_inputs


def test_opponents_feed_only_history_and_keep_real_missing_runs_separate_from_padding():
    source = opponent_inputs()
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3)
    prepared = prepare_nn_dataset(source, config)
    baseline = prepare_nn_dataset(dataset_inputs(future_rate=.4), config)
    assert prepared.preprocessing.current == baseline.preprocessing.current
    assert prepared.partitions == baseline.partitions
    assert not any(name.startswith("opp_") for name in prepared.preprocessing.current.numeric_names)
    sample = prepared.split("train")[0]
    rate = prepared.preprocessing.history.numeric_names.index("opp_horse_place_mean")
    coverage = prepared.preprocessing.history.numeric_names.index("opp_horse_place_coverage")
    np.testing.assert_array_equal(sample["history_mask"][0], [True, True, False])
    np.testing.assert_array_equal(sample["history_numeric_missing"][0, :, rate], [False, True, False])
    assert not sample["history_numeric_missing"][0, 1, coverage]
    assert not sample["history_mask"][1].any()  # New horse remains in the current field.
    batch = collate_nn_races([sample, prepared.split("validation")[0]])
    assert batch["history_numeric"].shape == (2, 2, 3, len(prepared.preprocessing.history.numeric_names))


def test_future_opponent_values_do_not_change_training_transforms_or_samples():
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3)
    original = prepare_nn_dataset(opponent_inputs(future_rate=.75), config)
    changed = prepare_nn_dataset(opponent_inputs(future_rate=1), config)
    assert original.preprocessing == changed.preprocessing
    np.testing.assert_array_equal(original.split("train")[0]["history_numeric"],
                                  changed.split("train")[0]["history_numeric"])
    assert not np.array_equal(original.split("validation")[0]["history_numeric"],
                              changed.split("validation")[0]["history_numeric"])


@pytest.mark.parametrize("name,value", [
    ("opp_count", None), ("opp_count", -1), ("opp_count", 1.5),
    ("opp_horse_place_mean", 1.1), ("opp_horse_place_mean", float("inf")),
    ("opp_horse_place_std", .6), ("opp_horse_starts_mean", -1),
    ("opp_horse_place_coverage", .3), ("opp_horse_place_coverage", None),
    ("opp_horse_place_coverage", 0),
])
def test_invalid_opponent_values_are_rejected_at_the_public_input_boundary(name, value):
    inputs = opponent_inputs()
    history = inputs.inputs.history
    history.loc[0, name] = value
    with pytest.raises(NnInputContractError):
        replace_inputs(inputs, history=history)


def test_no_opponents_is_distinct_from_opponents_with_missing_statistics():
    inputs = opponent_inputs()
    history = inputs.inputs.history
    for name in inputs.inputs.query.history_context_names:
        history.loc[0, name] = 0 if name == "opp_count" else None
    result = replace_inputs(inputs, history=history)
    assert result.inputs.history.opp_count.iloc[0] == 0
    assert result.inputs.history.opp_horse_place_coverage.isna().iloc[0]
    assert result.inputs.history.opp_horse_place_coverage.iloc[1] == 0
    history.loc[0, "opp_horse_place_coverage"] = 0
    with pytest.raises(NnInputContractError, match="empty opponent"):
        replace_inputs(inputs, history=history)


def test_history_context_cannot_be_reclassified_as_current_inputs_or_results():
    base = opponent_inputs().inputs
    with pytest.raises(NnInputContractError, match="cannot be current"):
        replace(base.contract, pre_race=(*base.contract.pre_race, *base.contract.history_context), history_context=())
    with pytest.raises(NnInputContractError, match="historical result"):
        replace(base.contract, history_results=(*base.contract.history_results, *base.contract.history_context), history_context=())
    with pytest.raises(NnInputContractError, match="version 1"):
        replace(base.contract, version=1)
    with pytest.raises(NnInputContractError, match="current feature"):
        NnRaceInputs(base.entries, base.history,
                     query=replace(base.query, feature_names=(*base.query.feature_names, "opp_count")),
                     contract=base.contract, source_revision=base.source_revision, captured_at=base.captured_at)
    with pytest.raises(NnInputContractError, match="historical context"):
        replace(base.contract, history_context=(NnFeatureField("result_order", "numeric"),), history_results=())
