"""Train-only numerical statistics and category vocabularies. No external I/O."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import NnFeatureField, NnInputContractError, NnRaceInputs, STATS_FLAGS


PAD_CATEGORY = 0
UNKNOWN_CATEGORY = 1
MISSING_CATEGORY = 2


@dataclass(frozen=True)
class NnNumericState:
    name: str
    mean: float
    scale: float

    def __post_init__(self):
        if not np.isfinite(self.mean) or not np.isfinite(self.scale) or self.scale <= 0:
            raise NnInputContractError("invalid fitted numeric statistics")


@dataclass(frozen=True)
class NnCategoryState:
    name: str
    values: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(self.values))
        if any(not isinstance(value, str) for value in self.values) or len(set(self.values)) != len(self.values):
            raise NnInputContractError("invalid fitted category vocabulary")

    @property
    def cardinality(self) -> int:
        return len(self.values) + 3


@dataclass(frozen=True)
class NnTablePreprocessor:
    numeric: tuple[NnNumericState, ...]
    categorical: tuple[NnCategoryState, ...]

    def __post_init__(self):
        object.__setattr__(self, "numeric", tuple(self.numeric))
        object.__setattr__(self, "categorical", tuple(self.categorical))
        names = [state.name for state in (*self.numeric, *self.categorical)]
        if len(set(names)) != len(names):
            raise NnInputContractError("duplicate preprocessing field")

    @property
    def numeric_names(self) -> tuple[str, ...]:
        return tuple(state.name for state in self.numeric)

    @property
    def categorical_names(self) -> tuple[str, ...]:
        return tuple(state.name for state in self.categorical)

    def transform(self, frame: pd.DataFrame) -> dict[str, np.ndarray]:
        numeric = np.zeros((len(frame), len(self.numeric)), dtype=np.float32)
        missing = np.zeros_like(numeric, dtype=bool)
        categorical = np.zeros((len(frame), len(self.categorical)), dtype=np.int64)
        for column, state in enumerate(self.numeric):
            values = frame[state.name].to_numpy(dtype=np.float64, na_value=np.nan)
            missing[:, column] = np.isnan(values)
            with np.errstate(over="ignore", invalid="ignore"):
                numeric[:, column] = (np.where(np.isnan(values), state.mean, values) - state.mean) / state.scale
        if not np.isfinite(numeric).all():
            raise NnInputContractError("numeric features overflow float32 after preprocessing")
        for column, state in enumerate(self.categorical):
            lookup = {value: index + 3 for index, value in enumerate(state.values)}
            categorical[:, column] = frame[state.name].map(lookup).fillna(UNKNOWN_CATEGORY).to_numpy(dtype=np.int64)
            categorical[frame[state.name].isna().to_numpy(), column] = MISSING_CATEGORY
        return {"numeric": numeric, "numeric_missing": missing, "categorical": categorical}


@dataclass(frozen=True)
class NnPreprocessingState:
    current: NnTablePreprocessor
    history: NnTablePreprocessor


def nn_feature_fields(inputs: NnRaceInputs) -> tuple[tuple[NnFeatureField, ...], tuple[NnFeatureField, ...]]:
    lookup = {field.name: field for field in (*inputs.contract.pre_race, *inputs.contract.history_results)}
    shared = tuple(lookup[name] for name in inputs.query.feature_names)
    flags = tuple(NnFeatureField(name, "numeric") for name in STATS_FLAGS)
    current = (*shared, *flags, NnFeatureField("days_since_last_run", "numeric"))
    history = (*shared, *(lookup[name] for name in inputs.query.history_result_names), *flags)
    return current, history


def fit_table_preprocessor(frame: pd.DataFrame, fields: tuple[NnFeatureField, ...]) -> NnTablePreprocessor:
    numeric, categorical = [], []
    for field in fields:
        if field.kind == "numeric":
            values = frame[field.name].dropna().to_numpy(dtype=np.float64)
            mean = float(values.mean()) if len(values) else 0.0
            scale = float(values.std()) if len(values) else 1.0
            numeric.append(NnNumericState(field.name, mean, scale if scale > 0 else 1.0))
        else:
            categorical.append(NnCategoryState(field.name, tuple(sorted(frame[field.name].dropna().unique()))))
    return NnTablePreprocessor(tuple(numeric), tuple(categorical))


def validate_preprocessing_schema(inputs: NnRaceInputs, state: NnPreprocessingState) -> None:
    for fields, table in zip(nn_feature_fields(inputs), (state.current, state.history), strict=True):
        if (tuple(field.name for field in fields if field.kind == "numeric") != table.numeric_names
                or tuple(field.name for field in fields if field.kind == "categorical") != table.categorical_names):
            raise NnInputContractError("input feature order/kinds differ from fitted preprocessing")
