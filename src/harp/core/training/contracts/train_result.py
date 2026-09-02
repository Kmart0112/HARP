from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import pandas as pd


@dataclass(frozen=True)
class TrainResult:
    model: lgb.LGBMClassifier
    feature_importance: pd.DataFrame
    metrics: dict[str, float | None]
    platt_info: dict[str, Any] | None = None
