"""Unsafe values must not enter an NN input bundle, regardless of its provider."""
from datetime import UTC, datetime

import pytest

from harp.core.nn.contracts import NnInputContractError, NnRaceInputs
from tests.nn_input_support import feature_contract, input_query, input_tables


@pytest.mark.parametrize("fault,message", [
    ("infinite_feature", "numeric"), ("floating_id", "IDs"),
    ("invalid_history_value", "numeric"), ("future_stats", "cutoff"),
    ("current_target", "columns"), ("same_day_endpoint", "endpoint"),
])
def test_input_bundle_rejects_unsafe_values(fault, message):
    entries, history, _ = input_tables()
    history = history.iloc[:3].copy()
    if fault == "infinite_feature":
        entries["age"] = float("inf")
    elif fault == "floating_id":
        entries["race_id"] = 2.026061301010101e16
    elif fault == "invalid_history_value":
        history["jockey_place_rate_3y_smooth"] = "not-a-number"
    elif fault == "future_stats":
        history.loc[0, "monthly_stats_cutoff"] = "2026-05-01"
    elif fault == "current_target":
        entries["result_order"] = 1
    elif fault == "same_day_endpoint":
        history.loc[1, "held_date"] = "2026-06-13"
    with pytest.raises(NnInputContractError, match=message):
        NnRaceInputs(entries, history, query=input_query(), contract=feature_contract(),
                     source_revision="fixture", captured_at=datetime(2026, 6, 21, tzinfo=UTC))
