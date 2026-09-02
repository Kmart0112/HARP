from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm


@dataclass(frozen=True)
class GroupConditionGlmmData:
    """Numerical design data for a group + condition GLMM."""

    y: np.ndarray
    group_idx: np.ndarray
    group_codes: tuple[str, ...]
    condition: np.ndarray
    condition_center: float
    condition_scale: float
    fixed_design: dict[str, np.ndarray]
    fixed_feature_names: tuple[str, ...]

    @property
    def n_obs(self) -> int:
        return int(self.y.shape[0])

    @property
    def n_groups(self) -> int:
        return int(len(self.group_codes))


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


def prepare_group_condition_glmm_data(
    df: pd.DataFrame,
    *,
    outcome_col: str,
    group_col: str,
    condition_col: str,
    odds_col: str | None = None,
    extra_fixed_effect_cols: list[str] | None = None,
    odds_floor: float = 1e-6,
    center_condition: bool = True,
    scale_condition: bool = True,
    drop_null_rows: bool = True,
) -> GroupConditionGlmmData:
    """Convert tabular data into arrays for a group + condition GLMM."""
    extras = list(extra_fixed_effect_cols or [])
    required_cols = [outcome_col, group_col, condition_col, *extras]
    if odds_col is not None:
        required_cols.append(odds_col)
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise KeyError(f"Required columns are missing: {missing}")
    if len(df) == 0:
        raise ValueError("Input dataframe is empty.")

    df_work = df.loc[:, required_cols].copy()
    if drop_null_rows:
        original_rows = len(df_work)
        df_work = df_work.dropna(subset=required_cols)
        if len(df_work) == 0:
            raise ValueError(
                "All rows were dropped due to nulls in required columns. "
                f"original_rows={original_rows}, required_cols={required_cols}"
            )

    y = _coerce_binary_outcome(df_work[outcome_col], outcome_col)

    condition_raw = pd.to_numeric(df_work[condition_col], errors="coerce")
    if condition_raw.isna().any():
        raise ValueError(f"`{condition_col}` contains non-numeric or NA rows.")
    condition_np = condition_raw.to_numpy(dtype="float64", copy=True)
    condition_center = float(condition_np.mean()) if center_condition else 0.0
    centered = condition_np - condition_center
    if scale_condition:
        condition_scale = float(centered.std(ddof=0))
        if condition_scale <= 0.0:
            condition_scale = 1.0
    else:
        condition_scale = 1.0
    condition = centered / condition_scale

    group_cat = df_work[group_col].astype("string").fillna("__NA__").astype("category")
    group_idx = group_cat.cat.codes.to_numpy(dtype="int64", copy=True)
    group_codes = tuple(str(code) for code in group_cat.cat.categories.tolist())
    if len(group_codes) < 2:
        raise ValueError("At least 2 group categories are required.")

    fixed_design: dict[str, np.ndarray] = {}
    fixed_feature_names: list[str] = []
    if odds_col is not None:
        odds = pd.to_numeric(df_work[odds_col], errors="coerce")
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
        values = pd.to_numeric(df_work[col], errors="coerce")
        if values.isna().any():
            raise ValueError(f"`{col}` contains non-numeric or NA rows.")
        fixed_design[col] = values.to_numpy(dtype="float64", copy=True)
        fixed_feature_names.append(col)

    return GroupConditionGlmmData(
        y=y,
        group_idx=group_idx,
        group_codes=group_codes,
        condition=condition.astype("float64"),
        condition_center=condition_center,
        condition_scale=float(condition_scale),
        fixed_design=fixed_design,
        fixed_feature_names=tuple(fixed_feature_names),
    )


def build_group_condition_glmm_model(
    data: GroupConditionGlmmData,
    *,
    model_name: str | None = None,
) -> pm.Model:
    """Create GLMM: logit(p)=b0+sum_k(bk*xk)+bc*condition+u_g+v_g*condition."""
    model_ctx = pm.Model(name=model_name) if model_name else pm.Model()
    with model_ctx as model:
        condition = pm.Data("condition", data.condition)
        group_idx = pm.Data("group_idx", data.group_idx)

        beta0 = pm.Normal("beta0", mu=0.0, sigma=2.0)
        beta_condition = pm.Normal("beta_condition", mu=0.0, sigma=1.0)

        eta = beta0 + beta_condition * condition
        for feature_name in data.fixed_feature_names:
            values = data.fixed_design[feature_name]
            feature_key = _sanitize_name(feature_name)
            x_var = pm.Data(f"x_{feature_key}", values)
            beta_var = pm.Normal(f"beta_{feature_key}", mu=0.0, sigma=1.0)
            eta = eta + beta_var * x_var

        sigma_group = pm.Exponential("sigma_group", lam=1.0)
        sigma_group_condition = pm.Exponential("sigma_group_condition", lam=1.0)

        group_intercept = pm.Normal(
            "group_intercept",
            mu=0.0,
            sigma=sigma_group,
            shape=data.n_groups,
        )
        group_condition = pm.Normal(
            "group_condition",
            mu=0.0,
            sigma=sigma_group_condition,
            shape=data.n_groups,
        )

        eta = eta + group_intercept[group_idx] + group_condition[group_idx] * condition

        pm.Deterministic("p", pm.math.sigmoid(eta))
        pm.Bernoulli("y_obs", logit_p=eta, observed=data.y)

    return model


def sample_group_condition_glmm(
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
    """Run MCMC sampling for the group + condition GLMM."""
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
