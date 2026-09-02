from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm

from harp.core.modeling.group_condition_glmm import (
    GroupConditionGlmmData,
    build_group_condition_glmm_model,
    prepare_group_condition_glmm_data,
    sample_group_condition_glmm,
)


@dataclass(frozen=True)
class JockeyDistanceGlmmData:
    """Numerical design data for the jockey-distance GLMM."""

    y: np.ndarray
    log_odds: np.ndarray
    distance: np.ndarray
    jockey_idx: np.ndarray
    jockey_codes: tuple[str, ...]
    distance_center: float
    distance_scale: float

    @property
    def n_obs(self) -> int:
        return int(self.y.shape[0])

    @property
    def n_jockeys(self) -> int:
        return int(len(self.jockey_codes))


def _to_jockey_data(data: GroupConditionGlmmData) -> JockeyDistanceGlmmData:
    if "log_odds" not in data.fixed_design:
        raise KeyError("fixed_design must contain `log_odds`.")
    return JockeyDistanceGlmmData(
        y=data.y.astype("int64"),
        log_odds=data.fixed_design["log_odds"].astype("float64"),
        distance=data.condition.astype("float64"),
        jockey_idx=data.group_idx.astype("int64"),
        jockey_codes=data.group_codes,
        distance_center=float(data.condition_center),
        distance_scale=float(data.condition_scale),
    )


def _to_group_data(data: JockeyDistanceGlmmData) -> GroupConditionGlmmData:
    return GroupConditionGlmmData(
        y=data.y.astype("int64"),
        group_idx=data.jockey_idx.astype("int64"),
        group_codes=tuple(data.jockey_codes),
        condition=data.distance.astype("float64"),
        condition_center=float(data.distance_center),
        condition_scale=float(data.distance_scale),
        fixed_design={"log_odds": data.log_odds.astype("float64")},
        fixed_feature_names=("log_odds",),
    )


def prepare_jockey_distance_glmm_data(
    df: pd.DataFrame,
    *,
    outcome_col: str,
    odds_col: str,
    distance_col: str,
    jockey_col: str,
    odds_floor: float = 1e-6,
    center_distance: bool = True,
    scale_distance: bool = True,
) -> JockeyDistanceGlmmData:
    """Convert a tabular dataset into model-ready numeric arrays."""
    generalized = prepare_group_condition_glmm_data(
        df,
        outcome_col=outcome_col,
        group_col=jockey_col,
        condition_col=distance_col,
        odds_col=odds_col,
        extra_fixed_effect_cols=None,
        odds_floor=odds_floor,
        center_condition=center_distance,
        scale_condition=scale_distance,
    )
    return _to_jockey_data(generalized)


def build_jockey_distance_glmm_model(
    data: JockeyDistanceGlmmData,
    *,
    model_name: str | None = None,
) -> pm.Model:
    """Create the GLMM: logit(p)=b0+b1*log_odds+b2*distance+u_j+v_j*distance."""
    model = build_group_condition_glmm_model(_to_group_data(data), model_name=model_name)

    # Keep backwards-compatible names for notebook/test consumers.
    with model:
        pm.Deterministic("beta_distance", model["beta_condition"])
        pm.Deterministic("sigma_jockey", model["sigma_group"])
        pm.Deterministic("sigma_jockey_distance", model["sigma_group_condition"])
        pm.Deterministic("jockey_intercept", model["group_intercept"])
        pm.Deterministic("jockey_distance", model["group_condition"])

    return model


def sample_jockey_distance_glmm(
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
    """Run MCMC sampling for the jockey-distance GLMM."""
    return sample_group_condition_glmm(
        model,
        draws=draws,
        tune=tune,
        chains=chains,
        cores=cores,
        target_accept=target_accept,
        random_seed=random_seed,
        progressbar=progressbar,
    )
