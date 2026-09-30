import pandas as pd
import pytest

from harp.core.nn.dataset import prepare_nn_dataset
from harp.core.nn.split import NnDatasetConfig
from tests.nn_dataset_support import replace_inputs, win_dataset_inputs


@pytest.mark.parametrize("case,reason", [
    ("valid", None), ("missing", "missing_win_label"), ("tie", "dead_heat"),
    ("none", "no_winner"), ("inconsistent", "inconsistent_win_result"),
])
def test_win_preparation_admits_only_complete_single_winner_races(case, reason):
    source = win_dataset_inputs()
    targets = source.targets
    race = targets.race_id.eq("R3")
    if case == "missing":
        targets.loc[race & targets.kettonum.eq("H4"), "is_win"] = pd.NA
    elif case == "tie":
        targets.loc[race, ["is_win", "result_order"]] = [True, 1]
    elif case == "none":
        targets.loc[race, ["is_win", "result_order"]] = [False, 2]
    elif case == "inconsistent":
        targets.loc[race & targets.kettonum.eq("H1"), "result_order"] = 2
    # Place-label availability has no bearing on the win task.
    targets.loc[race, "is_place"] = pd.NA
    prepared = prepare_nn_dataset(replace_inputs(source, targets=targets),
                                  NnDatasetConfig("2026-06-13", "2026-06-20", 3, task="win"))
    assert next(p.exclusion_reason for p in prepared.partitions if p.race_id == "R3") == reason
    assert len(prepared.split("validation")) == (1 if reason is None else 0)
    assert prepared.split("train")[0]["labels"].tolist() == [1, 0]
    assert prepared.summary["validation"]["excluded_entries"] == (0 if reason is None else 2)


def test_win_preprocessing_does_not_learn_from_future_winners_or_features():
    source = win_dataset_inputs()
    config = NnDatasetConfig("2026-06-13", "2026-06-20", 3, task="win")
    before = prepare_nn_dataset(source, config)
    entries, targets = source.inputs.entries, source.targets
    entries.loc[entries.race_id.eq("R4"), "age"] = 99
    future = targets.race_id.eq("R4")
    targets.loc[future, "is_win"] = ~targets.loc[future, "is_win"]
    targets.loc[future, "result_order"] = targets.loc[future, "is_win"].map({True: 1, False: 2})
    after = prepare_nn_dataset(replace_inputs(source, entries=entries, targets=targets), config)
    assert before.preprocessing == after.preprocessing
    assert before.split("train")[0]["labels"].tolist() == after.split("train")[0]["labels"].tolist()
