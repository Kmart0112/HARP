from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..dataset_builder import BinaryDataset


@dataclass(frozen=True)
class YearHoldoutBuildInput:
    df_train: pd.DataFrame
    train_year_start: int
    train_year_end: int
    test_year: int
    feature_names: list[str]
    cat_features: list[str]
    target_col: str


@dataclass(frozen=True)
class ModelTrainInput:
    ds: BinaryDataset
    df_meta: pd.DataFrame | None = None
    odds_col: str | None = None
    train_year_start: int | None = None
    train_year_end: int | None = None


@dataclass(frozen=True)
class ModelPredictInput:
    payload: dict[str, Any]
    df_feat: pd.DataFrame


@dataclass(frozen=True)
class PlattCalibrationFitInput:
    model: Any
    ds: BinaryDataset
    df_meta: pd.DataFrame
    odds_col: str
    train_year_start: int
    train_year_end: int
    valid_years_back: int = 5
    eps: float = 1e-12


@dataclass(frozen=True)
class PlattCalibrationTransformInput:
    base_proba: np.ndarray
    payload: dict[str, Any]
    df_feat: pd.DataFrame
    odds_col: str | None = None
