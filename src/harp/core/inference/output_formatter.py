from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

OUTPUT_COLUMNS = [
    "held_date",
    "jyo_name",
    "round",
    "horse_number",
    "horse_name",
    "edge",
    "p_place",
    "kelly_fraction",
    "kelly_bet_amount",
    "surface",
    "distance_m",
    "popularity",
    "odds_fukusho_low",
    "odds_fukusho_high",
    "odds",
    "ev_return",
]


def get_next_weekend_dates(now: datetime) -> tuple[str, str]:
    today: date = now.date()
    weekday = today.weekday()  # Mon=0 ... Sat=5 Sun=6
    if weekday == 6:
        return today.isoformat(), today.isoformat()

    days_until_sat = (5 - weekday) % 7
    sat = today + timedelta(days=days_until_sat)
    sun = sat + timedelta(days=1)
    return sat.isoformat(), sun.isoformat()


def resolve_date_range(
    from_date: str | None,
    to_date: str | None,
    *,
    now: datetime,
) -> tuple[str, str]:
    if from_date is None and to_date is None:
        return get_next_weekend_dates(now)
    if from_date is None and to_date is not None:
        return to_date, to_date
    if from_date is not None and to_date is None:
        return from_date, from_date
    return from_date or "", to_date or ""


def ensure_merge_keys(df: pd.DataFrame, name: str) -> pd.DataFrame:
    required = ["race_id", "horse_number"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"{name} is missing required columns: {missing}")

    out = df.copy()
    out["race_id"] = out["race_id"].astype(str)
    out["horse_number"] = pd.to_numeric(out["horse_number"], errors="raise").astype(int)
    return out


def select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out.loc[:, OUTPUT_COLUMNS]
