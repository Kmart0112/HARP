"""Unsafe values must not enter an NN input bundle, regardless of its provider."""
from datetime import UTC, datetime
from dataclasses import replace

import pandas as pd
import pytest

from harp.core.nn.contracts import NnFeatureField, NnInputContractError, NnRaceInputs
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


@pytest.mark.parametrize("table", ["entries", "history"])
@pytest.mark.parametrize("count", [None, 0, 1])
def test_unknown_stats_cutoff_preserves_only_absent_statistics_and_zero_counts(table, count):
    entries, history, _ = input_tables()
    history = history.iloc[:3].copy()
    entries["sire_starts_5y"] = 0
    history["sire_starts_5y"] = 0
    frame = entries if table == "entries" else history
    frame.loc[0, ["monthly_stats_cutoff", "yearly_stats_cutoff", "jockey_place_rate_3y_smooth"]] = None
    frame.loc[0, "jockey_stats_missing"] = True
    frame["sire_starts_5y"] = frame.sire_starts_5y.astype("Int64")
    frame.loc[0, "sire_starts_5y"] = count
    contract = feature_contract()
    contract = replace(contract, pre_race=(*contract.pre_race, NnFeatureField("sire_starts_5y", "numeric")))
    query = replace(input_query(), feature_names=contract.pre_race_names)
    if count == 1:
        with pytest.raises(NnInputContractError, match="known cutoff"):
            NnRaceInputs(entries, history, query=query, contract=contract,
                         source_revision="fixture", captured_at=datetime(2026, 6, 21, tzinfo=UTC))
        return
    result = NnRaceInputs(entries, history, query=query, contract=contract,
                         source_revision="fixture", captured_at=datetime(2026, 6, 21, tzinfo=UTC))
    restored = result.entries if table == "entries" else result.history
    assert len(result.entries) == 3 and len(result.history) == 3
    assert pd.isna(restored.iloc[0].monthly_stats_cutoff)
    assert pd.isna(restored.iloc[0].yearly_stats_cutoff)
    assert pd.isna(restored.iloc[0].jockey_place_rate_3y_smooth)
    assert restored.iloc[0].jockey_stats_missing


@pytest.mark.parametrize("fault", ["known_rate", "missing_flag_false"])
def test_unknown_cutoff_cannot_hide_statistics_with_an_unverified_reference_date(fault):
    entries, history, _ = input_tables()
    history = history.iloc[:3].copy()
    entries.loc[0, "monthly_stats_cutoff"] = None
    if fault == "known_rate":
        entries.loc[0, "jockey_stats_missing"] = True
    else:
        entries.loc[0, "jockey_place_rate_3y_smooth"] = None
    with pytest.raises(NnInputContractError, match="known cutoff"):
        NnRaceInputs(entries, history, query=input_query(), contract=feature_contract(),
                     source_revision="fixture", captured_at=datetime(2026, 6, 21, tzinfo=UTC))
