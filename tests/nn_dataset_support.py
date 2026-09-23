"""Small full-field datasets spanning train, validation and test event dates."""
from datetime import UTC, datetime

import pandas as pd

from harp.core.nn.contracts import NnRaceInputs, NnTrainingInputs
from tests.nn_input_support import feature_contract, input_query, input_tables


def dataset_inputs(*, unknown_train_label=False, future_rate=50.0):
    entries, history, targets = input_tables()
    test = entries.iloc[[1]].copy()
    test["race_id"], test["held_date"] = "R4", "2026-06-21"
    test["kettonum"] = "H3"
    test["horse_number"], test["active_entrant_count"] = 1, 1
    test["sex_cd"] = "test_only"
    entries = pd.concat([entries, test], ignore_index=True)
    entries.loc[entries.race_id == "R3", "sex_cd"] = "validation_only"
    entries.loc[entries.race_id == "R3", "jockey_place_rate_3y_smooth"] = future_rate
    history = history.iloc[:3].copy()
    # Run 3 is R2 itself: available to the later R3 target, never to R2.
    history.loc[history.run_no == 3, "jockey_place_rate_3y_smooth"] = future_rate
    history.loc[history.run_no == 3, "result_status_code"] = "future_only"
    targets = entries[["race_id", "kettonum"]].merge(targets, how="left", on=["race_id", "kettonum"])
    targets.loc[targets.race_id == "R4", ["result_order", "is_win", "is_place"]] = [2, 0, 1]
    if not unknown_train_label:
        targets.loc[(targets.race_id == "R2") & (targets.kettonum == "H2"), ["result_order", "is_win", "is_place"]] = [3, 0, 0]
    base = NnRaceInputs(entries, history, query=input_query(to_date="2026-06-21"), contract=feature_contract(),
                        source_revision="dataset-fixture", captured_at=datetime(2026, 6, 22, tzinfo=UTC))
    return NnTrainingInputs(base, targets)


def replace_inputs(inputs, *, entries=None, history=None, targets=None):
    base = inputs.inputs
    replacement = NnRaceInputs(
        base.entries if entries is None else entries,
        base.history if history is None else history,
        query=base.query, contract=base.contract, source_revision=base.source_revision, captured_at=base.captured_at,
    )
    return NnTrainingInputs(replacement, inputs.targets if targets is None else targets)
