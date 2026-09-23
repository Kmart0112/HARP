import numpy as np
import pytest

from harp.core.nn.contracts import NnInputContractError
from harp.core.nn.dataset import NnRaceDataset, collate_nn_races, prepare_nn_dataset, restore_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from tests.nn_dataset_support import dataset_inputs, replace_inputs


def test_full_fields_are_split_by_date_and_history_stops_before_each_target():
    prepared = prepare_nn_dataset(dataset_inputs(), NnDatasetConfig("2026-06-13", "2026-06-20", 2))
    assert prepared.split("train").race_ids == ("R2",)
    assert prepared.split("validation").race_ids == ("R3",)
    assert prepared.split("test").race_ids == ("R4",)
    train = prepared.split("train")[0]
    validation = prepared.split("validation")[0]
    assert train["horse_ids"] == ("H1", "H2")
    np.testing.assert_array_equal(train["labels"], [1, 0])
    np.testing.assert_array_equal(train["history_mask"], [[True, True], [False, False]])
    # Train's past rates .10 and .20 standardize to -1 and +1. Its own run is not included.
    column = prepared.preprocessing.history.numeric_names.index("jockey_place_rate_3y_smooth")
    np.testing.assert_allclose(train["history_numeric"][0, :, column], [-1, 1])
    np.testing.assert_allclose(validation["history_numeric"][0, :, column], [1, 997])
    np.testing.assert_allclose(train["history_relative"][0, :, 0], np.log1p([73, 12]))
    np.testing.assert_allclose(train["history_relative"][0, :, 1], [.5, 0])
    np.testing.assert_allclose(validation["history_relative"][0, :, 0], np.log1p([19, 7]))


def test_fitting_uses_only_train_and_its_selected_history_even_when_future_values_change():
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 1)
    first = prepare_nn_dataset(dataset_inputs(future_rate=50), config)
    changed = prepare_nn_dataset(dataset_inputs(future_rate=50000), config)
    assert first.preprocessing == changed.preprocessing
    # K=1 discards the earlier .1 row from fitting too, leaving only .2.
    rate = next(state for state in first.preprocessing.history.numeric if state.name == "jockey_place_rate_3y_smooth")
    assert rate.mean == pytest.approx(.2)
    assert first.preprocessing.current.categorical[0].values == ("1",)
    status = next(state for state in first.preprocessing.history.categorical if state.name == "result_status_code")
    assert status.values == ("4",)


def test_padding_missing_features_unknown_categories_and_unknown_labels_are_distinct():
    inputs = dataset_inputs()
    prepared = prepare_nn_dataset(inputs, NnDatasetConfig("2026-06-13", "2026-06-20", 3))
    train, validation = prepared.dataset[0], prepared.dataset[1]
    batch = collate_nn_races([train, validation])
    assert batch["race_ids"] == ("R2", "R3")
    assert batch["horse_ids"] == (("H1", "H2"), ("H1", None))
    np.testing.assert_array_equal(batch["entrant_mask"], [[True, True], [True, False]])
    np.testing.assert_array_equal(batch["history_mask"][0], [[True, True, False], [False, False, False]])
    assert batch["current_numeric"].dtype == np.float32
    assert batch["history_categorical"].dtype == np.int64
    column = prepared.preprocessing.current.numeric_names.index("jockey_place_rate_3y_smooth")
    assert batch["current_numeric_missing"][0, 1, column]
    assert batch["current_numeric"][0, 1, column] == 0
    # PAD=0, UNK=1, MISSING=2, learned values >=3.
    assert batch["current_categorical"][1, 0, 0] == 1
    assert batch["current_categorical"][1, 1, 0] == 0
    status = prepared.preprocessing.history.categorical_names.index("result_status_code")
    np.testing.assert_array_equal(batch["history_categorical"][0, 0, :, status], [2, 3, 0])
    # A DNF is an existing history record with a missing outcome, not history padding.
    result_column = prepared.preprocessing.history.numeric_names.index("result_order")
    assert batch["history_numeric_missing"][0, 0, 1, result_column]
    assert batch["history_mask"][0, 0, 1]
    for key in ("history_numeric", "history_categorical", "history_relative", "labels", "label_mask"):
        assert not batch[key][1, 1].any()
    prediction = NnRaceDataset(inputs.inputs, prepared.preprocessing, 3)[0]
    assert prediction["entrant_mask"].all()
    assert not prediction["label_mask"].any()
    for key in ("current_numeric", "history_numeric", "current_categorical", "history_categorical"):
        np.testing.assert_array_equal(prediction[key], train[key])


def test_incomplete_labels_exclude_whole_race_and_do_not_fit_its_features():
    inputs = dataset_inputs(unknown_train_label=True)
    prepared = prepare_nn_dataset(inputs, NnDatasetConfig("2026-06-20", "2026-06-21", 1))
    assert prepared.split("train").race_ids == ("R3",)
    assert prepared.dataset[0]["horse_ids"] == ("H1", "H2")
    assert prepared.partitions[0].exclusion_reason == "missing_place_label"
    assert prepared.summary["train"] == dict(races=1, entries=1, excluded_races=1, excluded_entries=2)
    assert prepared.preprocessing.current.categorical[0].values == ("validation_only",)


def test_no_train_races_with_complete_labels_is_a_preparation_error():
    with pytest.raises(NnInputContractError, match="no fully labelled races"):
        prepare_nn_dataset(dataset_inputs(unknown_train_label=True), NnDatasetConfig("2026-06-13", "2026-06-20", 2))


def test_all_missing_numeric_history_and_empty_histories_stay_finite():
    inputs = dataset_inputs()
    entries, history = inputs.inputs.entries, inputs.inputs.history
    entries["age"], history["age"] = None, None
    inputs = replace_inputs(inputs, entries=entries, history=history)
    prepared = prepare_nn_dataset(inputs, NnDatasetConfig("2026-06-13", "2026-06-20", 1))
    column = prepared.preprocessing.history.numeric_names.index("age")
    sample = prepared.dataset[0]
    assert sample["history_numeric_missing"][0, 0, column]
    assert not sample["history_mask"][1].any()
    assert np.isfinite(sample["current_numeric"]).all()
    assert np.isfinite(sample["history_numeric"]).all()
    # Training can consist entirely of debutants; an empty fit vocabulary remains valid.
    entries = entries.loc[entries.kettonum != "H1"].copy()
    entries["active_entrant_count"] = 1
    targets = inputs.targets.loc[inputs.targets.kettonum != "H1"]
    debutants = replace_inputs(inputs, entries=entries, history=history.iloc[:0], targets=targets)
    first_starts = prepare_nn_dataset(debutants, NnDatasetConfig("2026-06-13", "2026-06-20", 2))
    assert first_starts.split("train")[0]["entrant_mask"].all()
    assert not first_starts.split("train")[0]["history_mask"].any()


def test_history_statistics_count_reused_runs_once():
    prepared = prepare_nn_dataset(dataset_inputs(future_rate=.4), NnDatasetConfig("2026-06-20", "2026-06-21", 3))
    rate = next(state for state in prepared.preprocessing.history.numeric if state.name == "jockey_place_rate_3y_smooth")
    # R0 and R1 are used by two targets; fit the union {.1,.2,.4} once.
    assert rate.mean == pytest.approx(7 / 30)


def test_input_and_target_order_and_sample_mutation_cannot_break_alignment():
    inputs = dataset_inputs()
    shuffled = replace_inputs(inputs, entries=inputs.inputs.entries.iloc[::-1], history=inputs.inputs.history.iloc[::-1], targets=inputs.targets.iloc[::-1])
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 2)
    first, second = prepare_nn_dataset(inputs, config), prepare_nn_dataset(shuffled, config)
    assert first.partitions == second.partitions
    assert first.preprocessing == second.preprocessing
    selected = second.dataset.select_races(("R4", "R2"))
    assert selected[1]["horse_ids"] == ("H1", "H2")
    for key in ("current_numeric", "history_numeric", "labels"):
        expected = first.dataset[0][key]
        sample = second.dataset[0]
        np.testing.assert_array_equal(sample[key], expected)
        sample[key][:] = -999
        np.testing.assert_array_equal(second.dataset[0][key], expected)


def test_replay_rejects_changed_labels_that_invalidate_saved_admission():
    prepared = prepare_nn_dataset(dataset_inputs(), NnDatasetConfig("2026-06-13", "2026-06-20", 2))
    with pytest.raises(NnInputContractError, match="saved splits differ"):
        restore_nn_dataset(dataset_inputs(unknown_train_label=True), prepared.config, prepared.preprocessing, prepared.partitions)


def test_prediction_rejects_changed_feature_order_instead_of_silently_mixing_columns():
    inputs = dataset_inputs()
    prepared = prepare_nn_dataset(inputs, NnDatasetConfig("2026-06-13", "2026-06-20", 2))
    from dataclasses import replace
    from harp.core.nn.contracts import NnRaceInputs
    base = inputs.inputs
    changed = NnRaceInputs(base.entries, base.history,
                          query=replace(base.query, feature_names=tuple(reversed(base.query.feature_names))),
                          contract=base.contract, source_revision=base.source_revision, captured_at=base.captured_at)
    with pytest.raises(NnInputContractError, match="order/kinds"):
        NnRaceDataset(changed, prepared.preprocessing, 2)
