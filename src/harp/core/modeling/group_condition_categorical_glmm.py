from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm


@dataclass(frozen=True)
class SparseFilterStats:
    """Row counts before/after sparse-category filtering."""

    n_rows_input: int
    n_rows_after_null_drop: int
    n_rows_after_sparse_filter: int

    @property
    def sparse_drop_ratio(self) -> float:
        if self.n_rows_after_null_drop <= 0:
            return 0.0
        dropped = self.n_rows_after_null_drop - self.n_rows_after_sparse_filter
        return float(dropped / self.n_rows_after_null_drop)


@dataclass(frozen=True)
class GroupConditionCategoricalGlmmData:
    """Numerical design data for a group + categorical-condition GLMM."""

    y: np.ndarray
    group_idx: np.ndarray
    group_codes: tuple[str, ...]
    condition_idx: np.ndarray
    condition_codes: tuple[str, ...]
    fixed_design: dict[str, np.ndarray]
    fixed_feature_names: tuple[str, ...]
    filter_stats: SparseFilterStats

    @property
    def n_obs(self) -> int:
        return int(self.y.shape[0])

    @property
    def n_groups(self) -> int:
        return int(len(self.group_codes))

    @property
    def n_conditions(self) -> int:
        return int(len(self.condition_codes))


def _sanitize_name(name: str) -> str:
    sanitized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(name))
    return sanitized.strip("_") or "x"


def _coerce_binary_outcome(values: pd.Series, column_name: str) -> np.ndarray:
    y_raw = pd.to_numeric(values, errors="coerce")
    if y_raw.isna().any():
        raise ValueError(f"`{column_name}` contains non-numeric or NA rows.")
    y = y_raw.astype(int).to_numpy(copy=True)
    unique_values = np.unique(y)
    if not set(unique_values.tolist()).issubset({0, 1}):
        raise ValueError(
            f"`{column_name}` must be binary 0/1. Found values: {unique_values.tolist()}"
        )
    return y.astype("int64")


def _apply_sparse_filters(
    df: pd.DataFrame,
    *,
    group_col: str,
    condition_col: str,
    min_group_count: int,
    min_cell_count: int,
    min_condition_levels_per_group: int,
) -> pd.DataFrame:
    if min_group_count < 1:
        raise ValueError("min_group_count must be >= 1")
    if min_cell_count < 1:
        raise ValueError("min_cell_count must be >= 1")
    if min_condition_levels_per_group < 1:
        raise ValueError("min_condition_levels_per_group must be >= 1")

    current = df.copy()
    while True:
        before_len = len(current)
        if before_len == 0:
            return current

        group_count = current.groupby(group_col, observed=True)[group_col].transform("size")
        cell_count = current.groupby([group_col, condition_col], observed=True)[group_col].transform(
            "size"
        )
        keep = (group_count >= min_group_count) & (cell_count >= min_cell_count)
        filtered = current.loc[keep].copy()
        if filtered.empty:
            return filtered

        cond_levels = (
            filtered.groupby(group_col, observed=True)[condition_col]
            .nunique()
            .rename("condition_levels")
        )
        valid_groups = cond_levels[cond_levels >= min_condition_levels_per_group].index
        filtered = filtered.loc[filtered[group_col].isin(valid_groups)].copy()

        if len(filtered) == before_len:
            return filtered
        current = filtered


def prepare_group_condition_categorical_glmm_data(
    df: pd.DataFrame,
    *,
    outcome_col: str,
    group_col: str,
    condition_col: str,
    odds_col: str | None = None,
    extra_fixed_effect_cols: list[str] | None = None,
    odds_floor: float = 1e-6,
    drop_null_rows: bool = True,
    min_group_count: int = 1,
    min_cell_count: int = 1,
    min_condition_levels_per_group: int = 1,
) -> GroupConditionCategoricalGlmmData:
    """Convert tabular data into arrays for a categorical-condition GLMM."""
    extras = list(extra_fixed_effect_cols or [])
    required_cols = [outcome_col, group_col, condition_col, *extras]
    if odds_col is not None:
        required_cols.append(odds_col)
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise KeyError(f"Required columns are missing: {missing}")
    if len(df) == 0:
        raise ValueError("Input dataframe is empty.")

    n_rows_input = len(df)
    df_work = df.loc[:, required_cols].copy()
    if drop_null_rows:
        df_work = df_work.dropna(subset=required_cols)
    if len(df_work) == 0:
        raise ValueError(
            "All rows were dropped due to nulls in required columns. "
            f"n_rows_input={n_rows_input}, required_cols={required_cols}"
        )
    n_rows_after_null_drop = len(df_work)

    df_filtered = _apply_sparse_filters(
        df_work,
        group_col=group_col,
        condition_col=condition_col,
        min_group_count=min_group_count,
        min_cell_count=min_cell_count,
        min_condition_levels_per_group=min_condition_levels_per_group,
    )
    if len(df_filtered) == 0:
        raise ValueError("No rows remain after sparse-category filtering.")

    y = _coerce_binary_outcome(df_filtered[outcome_col], outcome_col)

    group_cat = df_filtered[group_col].astype("string").fillna("__NA__").astype("category")
    condition_cat = (
        df_filtered[condition_col].astype("string").fillna("__NA__").astype("category")
    )

    group_idx = group_cat.cat.codes.to_numpy(dtype="int64", copy=True)
    condition_idx = condition_cat.cat.codes.to_numpy(dtype="int64", copy=True)
    group_codes = tuple(str(code) for code in group_cat.cat.categories.tolist())
    condition_codes = tuple(str(code) for code in condition_cat.cat.categories.tolist())

    if len(group_codes) < 2:
        raise ValueError("At least 2 group categories are required.")
    if len(condition_codes) < 2:
        raise ValueError("At least 2 condition categories are required.")

    fixed_design: dict[str, np.ndarray] = {}
    fixed_feature_names: list[str] = []
    if odds_col is not None:
        odds = pd.to_numeric(df_filtered[odds_col], errors="coerce")
        if odds.isna().any():
            raise ValueError(f"`{odds_col}` contains non-numeric or NA rows.")
        if (odds <= 0.0).any():
            raise ValueError(f"`{odds_col}` must be > 0 for log transform.")
        odds_clipped = np.clip(odds.to_numpy(copy=True), a_min=float(odds_floor), a_max=None)
        fixed_design["log_odds"] = np.log(odds_clipped).astype("float64")
        fixed_feature_names.append("log_odds")

    for col in extras:
        if col == "log_odds":
            raise ValueError("`extra_fixed_effect_cols` must not contain reserved name: log_odds")
        values = pd.to_numeric(df_filtered[col], errors="coerce")
        if values.isna().any():
            raise ValueError(f"`{col}` contains non-numeric or NA rows.")
        fixed_design[col] = values.to_numpy(dtype="float64", copy=True)
        fixed_feature_names.append(col)

    return GroupConditionCategoricalGlmmData(
        y=y,
        group_idx=group_idx,
        group_codes=group_codes,
        condition_idx=condition_idx,
        condition_codes=condition_codes,
        fixed_design=fixed_design,
        fixed_feature_names=tuple(fixed_feature_names),
        filter_stats=SparseFilterStats(
            n_rows_input=n_rows_input,
            n_rows_after_null_drop=n_rows_after_null_drop,
            n_rows_after_sparse_filter=len(df_filtered),
        ),
    )


def build_group_condition_categorical_glmm_model(
    data: GroupConditionCategoricalGlmmData,
    *,
    model_name: str | None = None,
) -> pm.Model:
    """Create GLMM with group and categorical-condition random effects."""
    model_ctx = pm.Model(name=model_name) if model_name else pm.Model()
    with model_ctx as model:
        group_idx = pm.Data("group_idx", data.group_idx)
        condition_idx = pm.Data("condition_idx", data.condition_idx)

        beta0 = pm.Normal("beta0", mu=0.0, sigma=2.0)
        eta = beta0
        for feature_name in data.fixed_feature_names:
            values = data.fixed_design[feature_name]
            feature_key = _sanitize_name(feature_name)
            x_var = pm.Data(f"x_{feature_key}", values)
            beta_var = pm.Normal(f"beta_{feature_key}", mu=0.0, sigma=1.0)
            eta = eta + beta_var * x_var

        sigma_group = pm.Exponential("sigma_group", lam=1.0)
        sigma_condition = pm.Exponential("sigma_condition", lam=1.0)
        sigma_group_condition = pm.Exponential("sigma_group_condition", lam=1.0)

        group_intercept = pm.Normal(
            "group_intercept",
            mu=0.0,
            sigma=sigma_group,
            shape=data.n_groups,
        )
        condition_intercept = pm.Normal(
            "condition_intercept",
            mu=0.0,
            sigma=sigma_condition,
            shape=data.n_conditions,
        )
        group_condition = pm.Normal(
            "group_condition",
            mu=0.0,
            sigma=sigma_group_condition,
            shape=(data.n_groups, data.n_conditions),
        )

        eta = (
            eta
            + group_intercept[group_idx]
            + condition_intercept[condition_idx]
            + group_condition[group_idx, condition_idx]
        )

        pm.Deterministic("p", pm.math.sigmoid(eta))
        pm.Bernoulli("y_obs", logit_p=eta, observed=data.y)
    return model


def sample_group_condition_categorical_glmm(
    model: pm.Model,
    *,
    draws: int = 1_000,
    tune: int = 1_000,
    chains: int = 4,
    cores: int | None = None,
    target_accept: float = 0.9,
    random_seed: int = 42,
    progressbar: bool = True,
):
    """Run MCMC sampling for categorical-condition GLMM."""
    resolved_cores = int(min(chains, 2)) if cores is None else int(cores)
    with model:
        return pm.sample(
            draws=int(draws),
            tune=int(tune),
            chains=int(chains),
            cores=resolved_cores,
            target_accept=float(target_accept),
            random_seed=int(random_seed),
            progressbar=bool(progressbar),
            return_inferencedata=True,
        )
