from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import arviz as az
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harp.adapters.driven.storage import (  # noqa: E402
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    save_dataframe_cache,
)
from harp.core.modeling import (  # noqa: E402
    build_group_condition_categorical_glmm_model,
    build_group_condition_glmm_model,
    prepare_group_condition_categorical_glmm_data,
    prepare_group_condition_glmm_data,
    sample_group_condition_categorical_glmm,
    sample_group_condition_glmm,
)
from harp.shared.paths import notebook_analysis_cache_dir  # noqa: E402
from pipeline.runtime_settings import load_pipeline_runtime_config  # noqa: E402


@dataclass(frozen=True)
class RunConfig:
    db_url: str
    table: str
    start_date: str
    race_level_min: int
    race_level_max: int
    row_limit: int
    use_cache: bool
    refresh_db: bool
    outcome_col: str
    group_col: str
    condition_col: str
    condition_type: str
    distance_bucket: str
    min_group_count: int
    min_cell_count: int
    min_condition_levels: int
    rope: float
    odds_col: str | None
    extra_fixed_cols: list[str]
    draws: int
    tune: int
    chains: int
    cores: int
    target_accept: float
    random_seed: int


def _parse_extra_cols(raw: str) -> list[str]:
    return [col.strip() for col in raw.split(",") if col.strip()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run group+condition GLMM from DB with CLI-configurable columns.",
    )
    parser.add_argument("--db-url", type=str, default="", help="PostgreSQL URL. Defaults to env HARP_DB_URL.")
    parser.add_argument("--table", type=str, default="mart.m_train_race_horse_past5")
    parser.add_argument("--start-date", type=str, default="2023-01-01")
    parser.add_argument("--race-level-min", type=int, default=1)
    parser.add_argument("--race-level-max", type=int, default=3)
    parser.add_argument("--row-limit", type=int, default=200_000)
    parser.add_argument("--no-cache", action="store_true", help="Disable cache read/write.")
    parser.add_argument("--refresh-db", action="store_true", help="Force DB read and overwrite cache.")

    parser.add_argument("--outcome-col", type=str, default="is_place")
    parser.add_argument("--group-col", type=str, default="jockey_cd")
    parser.add_argument("--condition-col", type=str, default="distance_m")
    parser.add_argument(
        "--condition-type",
        type=str,
        choices=["continuous", "categorical"],
        default="continuous",
    )
    parser.add_argument(
        "--distance-bucket",
        type=str,
        choices=["none", "4bin"],
        default="none",
        help="Apply bucket transform to condition-col before modeling.",
    )
    parser.add_argument("--min-group-count", type=int, default=100)
    parser.add_argument("--min-cell-count", type=int, default=5)
    parser.add_argument("--min-condition-levels", type=int, default=2)
    parser.add_argument("--rope", type=float, default=0.05)

    parser.add_argument("--odds-col", type=str, default="j_odds_tansho")
    parser.add_argument("--no-odds", action="store_true", help="Disable odds/log_odds feature.")
    parser.add_argument(
        "--extra-fixed-cols",
        type=str,
        default="pos4_agari_synergy_wavg5_recent",
        help="Comma separated fixed-effect columns.",
    )

    parser.add_argument("--draws", type=int, default=400)
    parser.add_argument("--tune", type=int, default=400)
    parser.add_argument("--chains", type=int, default=2)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--target-accept", type=float, default=0.90)
    parser.add_argument("--random-seed", type=int, default=42)

    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "notebook" / "lab" / "tmp" / "group_condition_glmm_runs"),
        help="Directory to save summary/ranking/config artifacts.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Optional run name prefix for output files.",
    )
    return parser.parse_args()


def _validate_table_name(table_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", table_name):
        raise ValueError(f"Invalid table name: {table_name}")


def _build_config(args: argparse.Namespace) -> RunConfig:
    runtime_config = load_pipeline_runtime_config()
    db_url = args.db_url.strip() or runtime_config.database.db_url
    if not db_url:
        raise ValueError("db-url is required (either --db-url or HARP_DB_URL).")
    if args.race_level_min > args.race_level_max:
        raise ValueError("race-level-min must be <= race-level-max")
    if args.row_limit <= 0:
        raise ValueError("row-limit must be positive")
    if args.rope <= 0.0:
        raise ValueError("rope must be > 0")

    odds_col = None if args.no_odds else args.odds_col.strip()
    if odds_col == "":
        odds_col = None

    _validate_table_name(args.table)

    return RunConfig(
        db_url=db_url,
        table=args.table,
        start_date=args.start_date,
        race_level_min=int(args.race_level_min),
        race_level_max=int(args.race_level_max),
        row_limit=int(args.row_limit),
        use_cache=not bool(args.no_cache),
        refresh_db=bool(args.refresh_db),
        outcome_col=args.outcome_col.strip(),
        group_col=args.group_col.strip(),
        condition_col=args.condition_col.strip(),
        condition_type=str(args.condition_type).strip(),
        distance_bucket=str(args.distance_bucket).strip(),
        min_group_count=int(args.min_group_count),
        min_cell_count=int(args.min_cell_count),
        min_condition_levels=int(args.min_condition_levels),
        rope=float(args.rope),
        odds_col=odds_col,
        extra_fixed_cols=_parse_extra_cols(args.extra_fixed_cols),
        draws=int(args.draws),
        tune=int(args.tune),
        chains=int(args.chains),
        cores=int(args.cores),
        target_accept=float(args.target_accept),
        random_seed=int(args.random_seed),
    )


def _build_cache_path(cfg: RunConfig) -> Path:
    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    extras_part = "none" if not cfg.extra_fixed_cols else "_".join(cfg.extra_fixed_cols)
    odds_part = cfg.odds_col if cfg.odds_col else "no_odds"
    stem = (
        f"group_condition_{cfg.table.replace('.', '_')}_"
        f"{cfg.condition_type}_{cfg.distance_bucket}_"
        f"{cfg.outcome_col}_{cfg.group_col}_{cfg.condition_col}_{odds_part}_{extras_part}_"
        f"mg{cfg.min_group_count}_mc{cfg.min_cell_count}_ml{cfg.min_condition_levels}_"
        f"{cfg.start_date}_{cfg.race_level_min}_{cfg.race_level_max}_{cfg.row_limit}"
    )
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)
    return cache_dir / f"{safe_stem}.parquet"


def _load_dataset(cfg: RunConfig) -> pd.DataFrame:
    needed_cols = [cfg.outcome_col, cfg.group_col, cfg.condition_col, *cfg.extra_fixed_cols]
    if cfg.odds_col is not None:
        needed_cols.append(cfg.odds_col)
    select_cols = ["race_id", "held_date", "race_level", *needed_cols]

    seen: set[str] = set()
    select_cols_unique: list[str] = []
    for col in select_cols:
        if col not in seen:
            seen.add(col)
            select_cols_unique.append(col)

    cache_path = _build_cache_path(cfg)
    if cfg.use_cache and dataframe_cache_exists(cache_path) and (not cfg.refresh_db):
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading: {cache_source_path}")
        return load_dataframe_cache(cache_path)

    print(f"[db] querying: {cfg.table}")
    engine = create_engine(cfg.db_url)
    sql = text(
        f"""
        SELECT {", ".join(select_cols_unique)}
        FROM {cfg.table}
        WHERE held_date >= :start_date
          AND race_level BETWEEN :race_level_min AND :race_level_max
          AND {cfg.group_col} IS NOT NULL
        ORDER BY held_date, race_id
        LIMIT :row_limit
        """
    )
    with engine.connect().execution_options(stream_results=True) as conn:
        df = pd.read_sql_query(
            sql,
            conn,
            params={
                "start_date": cfg.start_date,
                "race_level_min": cfg.race_level_min,
                "race_level_max": cfg.race_level_max,
                "row_limit": cfg.row_limit,
            },
        )

    if df.empty:
        raise ValueError("Query returned 0 rows. Check filters and columns.")

    if cfg.use_cache:
        save_dataframe_cache(df, cache_path)
        print(f"[cache] saved: {cache_path}")

    return df


def _to_distance_bucket_4(series: pd.Series, source_col: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError(f"`{source_col}` contains non-numeric or NA rows for distance bucket.")

    bucket = pd.Series(index=series.index, dtype="object")
    bucket = bucket.mask(values <= 1400, "dist_le_1400")
    bucket = bucket.mask((values >= 1500) & (values <= 1700), "dist_1500_1700")
    bucket = bucket.mask((values >= 1800) & (values <= 2100), "dist_1800_2100")
    bucket = bucket.mask(values >= 2200, "dist_ge_2200")
    return bucket


def _resolve_condition_series(df: pd.DataFrame, cfg: RunConfig) -> tuple[pd.DataFrame, str]:
    if cfg.distance_bucket == "none":
        return df, cfg.condition_col

    derived_col = f"{cfg.condition_col}_bucket_4"
    out = df.copy()
    out[derived_col] = _to_distance_bucket_4(out[cfg.condition_col], cfg.condition_col)
    return out, derived_col


def _build_summary(idata) -> pd.DataFrame:
    preferred_var_names = [
        "beta0",
        "beta_log_odds",
        "beta_condition",
        "sigma_group",
        "sigma_condition",
        "sigma_group_condition",
    ]
    posterior_names = set(idata.posterior.data_vars.keys())
    var_names = [name for name in preferred_var_names if name in posterior_names]
    if not var_names:
        return pd.DataFrame()
    return az.summary(idata, var_names=var_names, kind="stats", hdi_prob=0.95)


def _build_group_ranking_continuous(idata, group_codes: tuple[str, ...]) -> pd.DataFrame:
    slope_mean = (
        idata.posterior["group_condition"].mean(dim=("chain", "draw")).to_numpy().reshape(-1)
    )
    intercept_mean = (
        idata.posterior["group_intercept"].mean(dim=("chain", "draw")).to_numpy().reshape(-1)
    )
    return (
        pd.DataFrame(
            {
                "group": list(group_codes),
                "condition_slope_mean": slope_mean,
                "intercept_mean": intercept_mean,
            }
        )
        .sort_values("condition_slope_mean", ascending=False, ignore_index=True)
    )


def _build_group_ranking_categorical(
    idata,
    group_codes: tuple[str, ...],
    condition_codes: tuple[str, ...],
    *,
    rope: float,
) -> pd.DataFrame:
    gc_samples = idata.posterior["group_condition"].to_numpy()
    flat = gc_samples.reshape((-1, gc_samples.shape[-2], gc_samples.shape[-1]))
    mean = flat.mean(axis=0)
    low = np.quantile(flat, 0.025, axis=0)
    high = np.quantile(flat, 0.975, axis=0)
    p_abs_gt_rope = np.mean(np.abs(flat) > float(rope), axis=0)

    rows: list[dict[str, object]] = []
    for g_idx, group_code in enumerate(group_codes):
        for c_idx, condition_code in enumerate(condition_codes):
            low_v = float(low[g_idx, c_idx])
            high_v = float(high[g_idx, c_idx])
            p_v = float(p_abs_gt_rope[g_idx, c_idx])
            rows.append(
                {
                    "group": group_code,
                    "condition": condition_code,
                    "effect_mean": float(mean[g_idx, c_idx]),
                    "hdi95_low": low_v,
                    "hdi95_high": high_v,
                    "p_abs_gt_rope": p_v,
                    "local_aptitude_flag": bool(((low_v > rope) or (high_v < -rope)) and (p_v >= 0.95)),
                }
            )

    return (
        pd.DataFrame(rows)
        .sort_values(["p_abs_gt_rope", "effect_mean"], ascending=[False, False], ignore_index=True)
    )


def _save_outputs(
    output_dir: Path,
    run_name: str,
    cfg: RunConfig,
    summary_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{run_name}_{ts}" if run_name else ts

    summary_path = output_dir / f"{prefix}_summary.csv"
    ranking_path = output_dir / f"{prefix}_group_ranking.csv"
    config_path = output_dir / f"{prefix}_config.json"

    summary_df.to_csv(summary_path, index=True)
    ranking_df.to_csv(ranking_path, index=False)
    config_path.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "summary": summary_path,
        "ranking": ranking_path,
        "config": config_path,
    }


def main() -> None:
    args = _parse_args()
    cfg = _build_config(args)
    output_dir = Path(args.output_dir)

    df_raw = _load_dataset(cfg)
    print(f"[data] rows={len(df_raw):,}")

    df_model, condition_col_resolved = _resolve_condition_series(df_raw, cfg)

    if cfg.condition_type == "continuous":
        if cfg.distance_bucket != "none":
            raise ValueError("distance-bucket is only supported with --condition-type categorical")

        glmm_data = prepare_group_condition_glmm_data(
            df_model,
            outcome_col=cfg.outcome_col,
            group_col=cfg.group_col,
            condition_col=condition_col_resolved,
            odds_col=cfg.odds_col,
            extra_fixed_effect_cols=cfg.extra_fixed_cols,
            center_condition=True,
            scale_condition=True,
        )
        print(
            f"[design] type=continuous n_obs={glmm_data.n_obs}, n_groups={glmm_data.n_groups}, "
            f"fixed={list(glmm_data.fixed_feature_names)}"
        )

        model = build_group_condition_glmm_model(glmm_data)
        idata = sample_group_condition_glmm(
            model,
            draws=cfg.draws,
            tune=cfg.tune,
            chains=cfg.chains,
            cores=cfg.cores,
            target_accept=cfg.target_accept,
            random_seed=cfg.random_seed,
            progressbar=True,
        )
        ranking_df = _build_group_ranking_continuous(idata, glmm_data.group_codes)
    else:
        glmm_data = prepare_group_condition_categorical_glmm_data(
            df_model,
            outcome_col=cfg.outcome_col,
            group_col=cfg.group_col,
            condition_col=condition_col_resolved,
            odds_col=cfg.odds_col,
            extra_fixed_effect_cols=cfg.extra_fixed_cols,
            min_group_count=cfg.min_group_count,
            min_cell_count=cfg.min_cell_count,
            min_condition_levels_per_group=cfg.min_condition_levels,
        )
        print(
            f"[design] type=categorical n_obs={glmm_data.n_obs}, n_groups={glmm_data.n_groups}, "
            f"n_conditions={glmm_data.n_conditions}, fixed={list(glmm_data.fixed_feature_names)}"
        )
        print(
            "[filter] "
            f"input={glmm_data.filter_stats.n_rows_input}, "
            f"after_null_drop={glmm_data.filter_stats.n_rows_after_null_drop}, "
            f"after_sparse={glmm_data.filter_stats.n_rows_after_sparse_filter}, "
            f"sparse_drop_ratio={glmm_data.filter_stats.sparse_drop_ratio:.4f}"
        )

        model = build_group_condition_categorical_glmm_model(glmm_data)
        idata = sample_group_condition_categorical_glmm(
            model,
            draws=cfg.draws,
            tune=cfg.tune,
            chains=cfg.chains,
            cores=cfg.cores,
            target_accept=cfg.target_accept,
            random_seed=cfg.random_seed,
            progressbar=True,
        )
        ranking_df = _build_group_ranking_categorical(
            idata,
            glmm_data.group_codes,
            glmm_data.condition_codes,
            rope=cfg.rope,
        )

    summary_df = _build_summary(idata)
    artifacts = _save_outputs(
        output_dir=output_dir,
        run_name=args.run_name.strip(),
        cfg=cfg,
        summary_df=summary_df,
        ranking_df=ranking_df,
    )

    print("[output]")
    for key, path in artifacts.items():
        print(f"- {key}: {path}")
    if not summary_df.empty:
        print("[summary_head]")
        print(summary_df.head())
    print("[ranking_head]")
    print(ranking_df.head(10))


if __name__ == "__main__":
    main()
