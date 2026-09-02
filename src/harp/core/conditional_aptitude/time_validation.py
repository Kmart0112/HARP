from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimeFold:
    fold_id: int
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    train_positions: np.ndarray
    validation_positions: np.ndarray


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    low: float
    high: float
    probability_below_zero: float
    repetitions: int


def build_expanding_window_folds(
    dates: pd.Series,
    *,
    validation_start: str | pd.Timestamp,
    validation_end: str | pd.Timestamp,
    validation_months: int,
    step_months: int,
) -> tuple[TimeFold, ...]:
    """Build leakage-safe expanding-window folds using half-open date ranges."""
    parsed_dates = pd.to_datetime(dates, errors="coerce").dt.tz_localize(None)
    if parsed_dates.isna().any():
        raise ValueError("time validation dates contain invalid values")
    if validation_months <= 0 or step_months <= 0:
        raise ValueError("validation_months and step_months must be > 0")

    start = pd.Timestamp(validation_start).tz_localize(None)
    end = pd.Timestamp(validation_end).tz_localize(None)
    if start >= end:
        raise ValueError("validation_start must be before validation_end")

    folds: list[TimeFold] = []
    fold_start = start
    fold_id = 0
    while fold_start < end:
        fold_end = min(fold_start + pd.DateOffset(months=validation_months), end)
        train_positions = np.flatnonzero((parsed_dates < fold_start).to_numpy())
        validation_positions = np.flatnonzero(
            ((parsed_dates >= fold_start) & (parsed_dates < fold_end)).to_numpy()
        )
        if len(train_positions) and len(validation_positions):
            folds.append(
                TimeFold(
                    fold_id=fold_id,
                    train_end=fold_start,
                    validation_start=fold_start,
                    validation_end=fold_end,
                    train_positions=train_positions,
                    validation_positions=validation_positions,
                )
            )
            fold_id += 1
        fold_start = fold_start + pd.DateOffset(months=step_months)
    return tuple(folds)


def build_inner_tuning_split(
    dates: pd.Series,
    *,
    outer_validation_start: str | pd.Timestamp,
    tuning_months: int,
) -> tuple[np.ndarray, np.ndarray]:
    parsed_dates = pd.to_datetime(dates, errors="coerce").dt.tz_localize(None)
    if parsed_dates.isna().any():
        raise ValueError("tuning dates contain invalid values")
    if tuning_months <= 0:
        raise ValueError("tuning_months must be > 0")
    tuning_end = pd.Timestamp(outer_validation_start).tz_localize(None)
    tuning_start = tuning_end - pd.DateOffset(months=tuning_months)
    train_positions = np.flatnonzero((parsed_dates < tuning_start).to_numpy())
    validation_positions = np.flatnonzero(
        ((parsed_dates >= tuning_start) & (parsed_dates < tuning_end)).to_numpy()
    )
    return train_positions, validation_positions


def block_bootstrap_mean(
    values: np.ndarray,
    blocks: pd.Series | np.ndarray,
    *,
    repetitions: int,
    confidence_level: float,
    random_seed: int,
) -> BootstrapInterval:
    """Bootstrap a mean by resampling complete temporal blocks."""
    metric_values = np.asarray(values, dtype=float)
    block_values = pd.Series(blocks, copy=False).astype("string").to_numpy(dtype=str)
    if metric_values.ndim != 1 or len(metric_values) != len(block_values):
        raise ValueError("bootstrap values and blocks must be equal-length vectors")
    if len(metric_values) == 0 or not np.all(np.isfinite(metric_values)):
        raise ValueError("bootstrap values must be non-empty and finite")
    if repetitions < 100:
        raise ValueError("bootstrap_repetitions must be >= 100")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")

    unique_blocks = np.unique(block_values)
    if len(unique_blocks) < 2:
        raise ValueError("block bootstrap requires at least two distinct blocks")
    positions_by_block = {
        block: np.flatnonzero(block_values == block) for block in unique_blocks
    }
    rng = np.random.default_rng(random_seed)
    samples = np.empty(repetitions, dtype=float)
    for repetition in range(repetitions):
        selected = rng.choice(unique_blocks, size=len(unique_blocks), replace=True)
        selected_positions = np.concatenate(
            [positions_by_block[block] for block in selected]
        )
        samples[repetition] = float(np.mean(metric_values[selected_positions]))

    alpha = 1.0 - confidence_level
    low, high = np.quantile(samples, [alpha / 2.0, 1.0 - alpha / 2.0])
    return BootstrapInterval(
        estimate=float(np.mean(metric_values)),
        low=float(low),
        high=float(high),
        probability_below_zero=float(np.mean(samples < 0.0)),
        repetitions=int(repetitions),
    )
