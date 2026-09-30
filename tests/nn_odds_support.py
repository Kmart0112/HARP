from datetime import UTC, datetime

import pandas as pd

from harp.core.nn.odds_targets import FinalPlaceOddsBatch, NnOddsSnapshot


def reference():
    return pd.DataFrame({"race_id": ["R1"] * 5 + ["R2"], "kettonum": [f"H{i}" for i in range(6)],
                         "horse_number": [1, 2, 3, 4, 5, 1],
                         "held_date": ["2024-01-01"] * 5 + ["2025-01-01"],
                         "split": ["train"] * 5 + ["test"]})


def quotes(entries=None):
    entries = reference() if entries is None else entries
    out = entries[["race_id", "horse_number"]].copy()
    out["place_low"], out["place_high"], out["source_found"] = 1.0, 2.0, True
    out["source_updated_at"] = pd.Timestamp("2026-09-25T00:00:00Z")
    return out


def batch(frame=None):
    return FinalPlaceOddsBatch(quotes() if frame is None else frame,
                              captured_at=datetime(2026, 9, 25, tzinfo=UTC),
                              source={"kind": "final", "revision": "fixture"})


def snapshot():
    frame = quotes()
    frame.loc[1, ["place_low", "place_high", "source_updated_at"]] = [None, None, pd.NaT]
    frame.loc[1, "source_found"] = False
    frame.loc[2, "place_low"] = None
    frame.loc[3, "place_low"] = 0.0
    return NnOddsSnapshot(reference(), batch(frame), prepared_dataset_id="a" * 64, input_dataset_id="b" * 64)
