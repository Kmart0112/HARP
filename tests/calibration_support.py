"""Frozen, point-in-time odds examples for calibration contracts."""
import pandas as pd

from harp.core.odds import OddsPolicy, select_odds
from harp.core.race_inputs import RaceInputs


def odds_inputs(prices, *, numbers=None):
    numbers = list(numbers) if numbers is not None else list(range(1, len(prices) + 1))
    entries = pd.DataFrame({"race_id": ["R"] * len(prices), "horse_number": numbers,
                            "kettonum": [f"H{number}" for number in numbers], "held_date": "2025-01-01",
                            "scheduled_start_at": pd.Timestamp("2025-01-01T03:00:00Z")})
    quotes = entries[["race_id", "horse_number"]].assign(win_odds=prices, place_low=prices, place_high=prices,
               win_popularity=1, published_at=pd.Timestamp("2025-01-01T02:50:00Z"), available_at=None)
    return RaceInputs(entries, select_odds(entries, quotes, OddsPolicy.pre_start(minutes=10, max_age_seconds=300)),
                      "odds-fixture", pd.Timestamp("2026-09-23T00:00:00Z").to_pydatetime())


def samples(probabilities, labels):
    return pd.DataFrame({"race_id": ["R"] * len(labels), "horse_number": list(range(1, len(labels) + 1)),
                         "kettonum": [f"H{number}" for number in range(1, len(labels) + 1)],
                         "held_date": "2025-01-01", "probability": probabilities, "y_true": labels})
