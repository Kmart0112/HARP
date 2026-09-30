import numpy as np
import pandas as pd
import pytest

from harp.core.nn.odds_targets import (
    FinalPlaceOddsQuery,
    NnOddsSnapshot,
    nn_odds_reference_hash,
)
from tests.nn_odds_support import batch, quotes, reference, snapshot


def test_teachers_align_by_identity_preserving_missing_rows_and_coverage():
    source = snapshot()
    shuffled = NnOddsSnapshot(reference().sample(frac=1, random_state=2),
                              batch(source.frame[quotes().columns].sample(frac=1, random_state=3)),
                              prepared_dataset_id="a" * 64, input_dataset_id="b" * 64)
    pd.testing.assert_frame_equal(shuffled.frame, source.frame)
    assert shuffled.frame.status.tolist() == ["available", "missing_row", "missing_value", "invalid_value", "available", "available"]
    assert shuffled.coverage.groupby("split").entries.sum().to_dict() == {"test": 1, "train": 5}
    assert shuffled.entry_keys_sha256 == nn_odds_reference_hash(reference().iloc[::-1])
    changed = shuffled.frame
    changed.loc[0, "place_low"] = 999
    assert shuffled.frame.loc[0, "place_low"] == 1


@pytest.mark.parametrize("low,high,status", [
    (1, 1, "available"), (0.99, 1, "invalid_value"), (3, 2, "invalid_value"),
    (np.inf, np.inf, "invalid_value"), (-np.inf, 2, "invalid_value"),
    (1, None, "missing_value"), (None, None, "missing_value"), (1234.5, 2345.6, "available"),
])
def test_price_validity_controls_only_the_auxiliary_teacher(low, high, status):
    frame = quotes()
    frame.loc[1, ["place_low", "place_high"]] = [low, high]
    result = NnOddsSnapshot(reference(), batch(frame), prepared_dataset_id="a" * 64, input_dataset_id="b" * 64)
    assert result.frame.status.iloc[1] == status
    assert len(result.frame) == 6


@pytest.mark.parametrize("fault", ["missing", "extra", "duplicate", "invalid_number", "float_id"])
def test_untrustworthy_identity_is_rejected_instead_of_positional_alignment(fault):
    frame = quotes()
    if fault == "missing":
        frame = frame.iloc[1:]
    elif fault == "extra":
        frame.loc[0, "race_id"] = "UNREQUESTED"
    elif fault == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    elif fault == "invalid_number":
        frame.loc[0, "horse_number"] = 0
    else:
        frame.loc[0, "race_id"] = 12345678901234568.0
    with pytest.raises(ValueError):
        NnOddsSnapshot(reference(), batch(frame), prepared_dataset_id="a" * 64, input_dataset_id="b" * 64)


def test_missing_train_teachers_cannot_be_reported_as_a_successful_capture():
    frame = quotes()
    frame.loc[frame.race_id.eq("R1"), "place_low"] = None
    with pytest.raises(ValueError, match="no available.*training"):
        NnOddsSnapshot(reference(), batch(frame), prepared_dataset_id="a" * 64, input_dataset_id="b" * 64)


def test_source_values_cannot_be_attached_to_an_absent_quote():
    frame = quotes()
    frame.loc[0, "source_found"] = False
    with pytest.raises(ValueError, match="absent"):
        batch(frame)


def test_query_rejects_duplicate_keys_and_does_not_expose_mutable_state():
    keys = reference()[["race_id", "horse_number"]]
    query = FinalPlaceOddsQuery(keys)
    keys.loc[0, "race_id"] = "CHANGED"
    assert query.keys.loc[0, "race_id"] == "R1"
    with pytest.raises(ValueError, match="duplicate"):
        FinalPlaceOddsQuery(pd.concat([keys, keys]))
