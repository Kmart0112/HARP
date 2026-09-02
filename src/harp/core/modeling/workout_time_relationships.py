from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


_WILSON_Z_95 = 1.959963984540054


@dataclass(frozen=True)
class WorkoutFeatureSpec:
    name: str
    family: str
    timing: str
    measure: str
    label: str


DEFAULT_WORKOUT_TIME_FEATURE_SPECS: tuple[WorkoutFeatureSpec, ...] = (
    WorkoutFeatureSpec("wood_lap_time_1", "wood", "current", "lap_1f", "直前ウッド 1F"),
    WorkoutFeatureSpec("wood_lap_time_2", "wood", "current", "lap_2f", "直前ウッド 2F"),
    WorkoutFeatureSpec("wood_haron_time_4", "wood", "current", "haron_4f", "直前ウッド 4F"),
    WorkoutFeatureSpec("hanro_lap_time_1", "hanro", "current", "lap_1f", "直前坂路 1F"),
    WorkoutFeatureSpec("hanro_lap_time_2", "hanro", "current", "lap_2f", "直前坂路 2F"),
    WorkoutFeatureSpec("hanro_haron_time_4", "hanro", "current", "haron_4f", "直前坂路 4F"),
    WorkoutFeatureSpec("week1_wood_lap_time_1", "wood", "week1", "lap_1f", "1週前ウッド 1F"),
    WorkoutFeatureSpec("week1_wood_lap_time_2", "wood", "week1", "lap_2f", "1週前ウッド 2F"),
    WorkoutFeatureSpec("week1_wood_haron_time_4", "wood", "week1", "haron_4f", "1週前ウッド 4F"),
    WorkoutFeatureSpec("week1_hanro_lap_time_1", "hanro", "week1", "lap_1f", "1週前坂路 1F"),
    WorkoutFeatureSpec("week1_hanro_lap_time_2", "hanro", "week1", "lap_2f", "1週前坂路 2F"),
    WorkoutFeatureSpec("week1_hanro_haron_time_4", "hanro", "week1", "haron_4f", "1週前坂路 4F"),
)

DEFAULT_WORKOUT_TIME_FEATURES: tuple[str, ...] = tuple(
    spec.name for spec in DEFAULT_WORKOUT_TIME_FEATURE_SPECS
)
_FEATURE_SPEC_MAP = {spec.name: spec for spec in DEFAULT_WORKOUT_TIME_FEATURE_SPECS}


def available_workout_features(
    df: pd.DataFrame,
    feature_names: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    requested = list(feature_names) if feature_names is not None else list(DEFAULT_WORKOUT_TIME_FEATURES)
    return [name for name in requested if name in df.columns]


def build_feature_catalog(
    feature_names: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    resolved_names = list(feature_names) if feature_names is not None else list(DEFAULT_WORKOUT_TIME_FEATURES)
    rows: list[dict[str, object]] = []
    for name in resolved_names:
        spec = _FEATURE_SPEC_MAP.get(name)
        if spec is None:
            continue
        rows.append(asdict(spec))
    return pd.DataFrame(rows)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _standardize(series: pd.Series) -> pd.Series:
    values = _coerce_numeric(series)
    mean = float(values.mean())
    std = float(values.std(ddof=0))
    if not np.isfinite(std) or std <= 0.0:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return (values - mean) / std


def _wilson_interval(successes: int, total: int, z: float = _WILSON_Z_95) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    phat = successes / total
    denom = 1.0 + (z**2 / total)
    center = (phat + z**2 / (2.0 * total)) / denom
    margin = (
        z
        * math.sqrt((phat * (1.0 - phat) / total) + (z**2 / (4.0 * total**2)))
        / denom
    )
    return (center - margin, center + margin)


def _rank_quantile_bucket(
    series: pd.Series,
    *,
    n_bins: int,
    ascending: bool,
) -> pd.Series:
    clean = _coerce_numeric(series).dropna()
    if clean.empty:
        return pd.Series(index=series.index, dtype="Int64")

    q = max(1, min(int(n_bins), int(clean.shape[0])))
    ranks = clean.rank(method="first", ascending=ascending)
    labels = pd.qcut(ranks, q=q, labels=False) + 1
    out = pd.Series(pd.NA, index=series.index, dtype="Int64")
    out.loc[clean.index] = labels.astype("int64")
    return out


def _fit_logistic_summary(
    design_df: pd.DataFrame,
    outcome: pd.Series,
    *,
    focus_col: str,
) -> dict[str, float]:
    local = design_df.copy()
    local["__y__"] = _coerce_numeric(outcome)
    local = local.dropna(axis=0, how="any")
    if local.empty:
        return {
            "n_obs": 0.0,
            "coef": math.nan,
            "auc": math.nan,
            "brier": math.nan,
            "logloss": math.nan,
        }

    y = local.pop("__y__").astype("int64")
    if y.nunique() < 2:
        return {
            "n_obs": float(local.shape[0]),
            "coef": math.nan,
            "auc": math.nan,
            "brier": math.nan,
            "logloss": math.nan,
        }

    x = local.astype("float64")
    model = LogisticRegression(max_iter=500, solver="lbfgs")
    model.fit(x, y)
    proba = model.predict_proba(x)[:, 1]
    coef_idx = list(x.columns).index(focus_col)
    return {
        "n_obs": float(local.shape[0]),
        "coef": float(model.coef_[0][coef_idx]),
        "auc": float(roc_auc_score(y, proba)),
        "brier": float(brier_score_loss(y, proba)),
        "logloss": float(log_loss(y, proba)),
    }


def build_availability_summary(
    df: pd.DataFrame,
    feature_names: list[str] | tuple[str, ...] | None = None,
    *,
    target_col: str = "is_place",
    win_col: str = "is_win",
) -> pd.DataFrame:
    features = available_workout_features(df, feature_names)
    if not features:
        return pd.DataFrame()
    catalog = build_feature_catalog(features).set_index("name", drop=False)
    rows: list[dict[str, object]] = []

    for feature_name in features:
        feature = _coerce_numeric(df[feature_name])
        non_null_mask = feature.notna()
        target = _coerce_numeric(df[target_col]) if target_col in df.columns else pd.Series(np.nan, index=df.index)
        win = _coerce_numeric(df[win_col]) if win_col in df.columns else pd.Series(np.nan, index=df.index)
        present_target = target.loc[non_null_mask]
        present_win = win.loc[non_null_mask]
        spec = catalog.loc[feature_name].to_dict() if feature_name in catalog.index else {"name": feature_name}

        rows.append(
            {
                **spec,
                "n_rows": int(len(df)),
                "n_present": int(non_null_mask.sum()),
                "present_rate": float(non_null_mask.mean()),
                "mean_time": float(feature.loc[non_null_mask].mean()) if non_null_mask.any() else math.nan,
                "median_time": float(feature.loc[non_null_mask].median()) if non_null_mask.any() else math.nan,
                "p10_time": float(feature.loc[non_null_mask].quantile(0.10)) if non_null_mask.any() else math.nan,
                "p90_time": float(feature.loc[non_null_mask].quantile(0.90)) if non_null_mask.any() else math.nan,
                "place_rate_when_present": float(present_target.mean()) if present_target.notna().any() else math.nan,
                "win_rate_when_present": float(present_win.mean()) if present_win.notna().any() else math.nan,
            }
        )

    return pd.DataFrame(rows)


def build_effect_summary(
    df: pd.DataFrame,
    feature_names: list[str] | tuple[str, ...] | None = None,
    *,
    target_col: str = "is_place",
    result_order_col: str = "result_order",
    control_cols: list[str] | tuple[str, ...] = ("surface", "distance_m", "race_level", "held_year"),
) -> pd.DataFrame:
    features = available_workout_features(df, feature_names)
    if not features:
        return pd.DataFrame()
    catalog = build_feature_catalog(features).set_index("name", drop=False)
    rows: list[dict[str, object]] = []

    for feature_name in features:
        local = pd.DataFrame(index=df.index)
        local["time_value"] = _coerce_numeric(df[feature_name])
        local["target"] = _coerce_numeric(df[target_col])
        local["result_order"] = _coerce_numeric(df[result_order_col]) if result_order_col in df.columns else np.nan
        for control_col in control_cols:
            if control_col in df.columns:
                local[control_col] = _coerce_numeric(df[control_col])

        local = local.dropna(subset=["time_value", "target"])
        if local.empty:
            continue

        local["fast_score"] = -_standardize(local["time_value"])
        unadjusted = _fit_logistic_summary(local[["fast_score"]], local["target"], focus_col="fast_score")

        adjusted_cols = ["fast_score", *[col for col in control_cols if col in local.columns]]
        adjusted = _fit_logistic_summary(local[adjusted_cols], local["target"], focus_col="fast_score")

        place_mask = local["target"] >= 0.5
        non_place_mask = local["target"] < 0.5
        if local["result_order"].notna().sum() >= 2:
            spearman_res = spearmanr(local["time_value"], local["result_order"], nan_policy="omit")
            spearman_corr = float(spearman_res.statistic)
            spearman_pvalue = float(spearman_res.pvalue)
        else:
            spearman_corr = math.nan
            spearman_pvalue = math.nan

        spec = catalog.loc[feature_name].to_dict() if feature_name in catalog.index else {"name": feature_name}
        rows.append(
            {
                **spec,
                "n_obs": int(local.shape[0]),
                "target_rate": float(local["target"].mean()),
                "mean_time_place": float(local.loc[place_mask, "time_value"].mean()) if place_mask.any() else math.nan,
                "mean_time_non_place": float(local.loc[non_place_mask, "time_value"].mean())
                if non_place_mask.any()
                else math.nan,
                "time_diff_place_minus_non_place": (
                    float(local.loc[place_mask, "time_value"].mean() - local.loc[non_place_mask, "time_value"].mean())
                    if place_mask.any() and non_place_mask.any()
                    else math.nan
                ),
                "spearman_time_vs_result_order": spearman_corr,
                "spearman_pvalue": spearman_pvalue,
                "coef_unadjusted_per_1sd_faster": unadjusted["coef"],
                "auc_unadjusted": unadjusted["auc"],
                "brier_unadjusted": unadjusted["brier"],
                "logloss_unadjusted": unadjusted["logloss"],
                "coef_adjusted_per_1sd_faster": adjusted["coef"],
                "auc_adjusted": adjusted["auc"],
                "brier_adjusted": adjusted["brier"],
                "logloss_adjusted": adjusted["logloss"],
                "n_obs_adjusted": int(adjusted["n_obs"]),
            }
        )

    return pd.DataFrame(rows)


def build_decile_summary(
    df: pd.DataFrame,
    feature_name: str,
    *,
    target_col: str = "is_place",
    result_order_col: str = "result_order",
    n_bins: int = 10,
) -> pd.DataFrame:
    if feature_name not in df.columns:
        raise KeyError(f"feature not found: {feature_name}")

    local = pd.DataFrame(
        {
            "time_value": _coerce_numeric(df[feature_name]),
            "target": _coerce_numeric(df[target_col]),
            "result_order": _coerce_numeric(df[result_order_col]) if result_order_col in df.columns else np.nan,
        }
    ).dropna(subset=["time_value", "target"])
    if local.empty:
        return pd.DataFrame()

    local["speed_decile"] = _rank_quantile_bucket(local["time_value"], n_bins=n_bins, ascending=True)
    grouped = (
        local.groupby("speed_decile", dropna=True)
        .agg(
            n_obs=("target", "size"),
            hit_count=("target", "sum"),
            target_rate=("target", "mean"),
            mean_time=("time_value", "mean"),
            min_time=("time_value", "min"),
            max_time=("time_value", "max"),
            mean_result_order=("result_order", "mean"),
        )
        .reset_index()
        .sort_values("speed_decile", ignore_index=True)
    )

    ci_low: list[float] = []
    ci_high: list[float] = []
    for _, row in grouped.iterrows():
        low, high = _wilson_interval(int(row["hit_count"]), int(row["n_obs"]))
        ci_low.append(low)
        ci_high.append(high)

    grouped["target_rate_ci_low"] = ci_low
    grouped["target_rate_ci_high"] = ci_high
    grouped["speed_band"] = grouped["speed_decile"].map(lambda x: f"{int(x):02d}")
    return grouped


def build_fast_slow_segment_summary(
    df: pd.DataFrame,
    feature_name: str,
    *,
    segment_col: str,
    target_col: str = "is_place",
    n_buckets: int = 4,
) -> pd.DataFrame:
    if feature_name not in df.columns:
        raise KeyError(f"feature not found: {feature_name}")
    if segment_col not in df.columns:
        raise KeyError(f"segment not found: {segment_col}")

    local = pd.DataFrame(
        {
            "time_value": _coerce_numeric(df[feature_name]),
            "target": _coerce_numeric(df[target_col]),
            "segment": df[segment_col],
        }
    ).dropna(subset=["time_value", "target", "segment"])
    if local.empty:
        return pd.DataFrame()

    local["speed_bucket"] = _rank_quantile_bucket(local["time_value"], n_bins=n_buckets, ascending=True)
    summary = (
        local.groupby(["segment", "speed_bucket"], dropna=True)
        .agg(
            n_obs=("target", "size"),
            target_rate=("target", "mean"),
            mean_time=("time_value", "mean"),
        )
        .reset_index()
    )

    fastest_bucket = 1
    slowest_bucket = int(summary["speed_bucket"].max())
    fastest = (
        summary.loc[summary["speed_bucket"] == fastest_bucket]
        .rename(
            columns={
                "n_obs": "n_fastest",
                "target_rate": "target_rate_fastest",
                "mean_time": "mean_time_fastest",
            }
        )
        .drop(columns=["speed_bucket"])
    )
    slowest = (
        summary.loc[summary["speed_bucket"] == slowest_bucket]
        .rename(
            columns={
                "n_obs": "n_slowest",
                "target_rate": "target_rate_slowest",
                "mean_time": "mean_time_slowest",
            }
        )
        .drop(columns=["speed_bucket"])
    )

    out = fastest.merge(slowest, on="segment", how="outer")
    out["delta_target_rate_fastest_minus_slowest"] = (
        out["target_rate_fastest"] - out["target_rate_slowest"]
    )
    return out.sort_values("delta_target_rate_fastest_minus_slowest", ascending=False, ignore_index=True)
