import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: ノートブックで使う依存を読み込む。
    import marimo as mo
    import arviz as az
    import numpy as np
    import pandas as pd
    import sys
    from pathlib import Path
    from pydantic import BaseModel, Field
    from sqlalchemy import create_engine, text

    return (
        BaseModel,
        Field,
        Path,
        az,
        create_engine,
        mo,
        pd,
        sys,
        text,
    )


@app.cell(hide_code=True)
def _(mo):
    # セル概要: ノートブックの目的を表示する。
    mo.md(r"""
    # Jockey Distance GLMM Validation (PyMC + marimo)

    dbt `mart.m_train_race_horse_past5` をDBから読み込み、騎手の距離適性をGLMMで検証する土台です。

    \[
    \text{logit}(p)=\beta_0+\beta_1\log(\text{odds})+\beta_2 \cdot distance + u_{jockey}+v_{jockey}\cdot distance
    \]
    """)
    return


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトのsrcとcache helperをimport可能にする。
    project_root = Path(__file__).resolve().parents[2]
    src_root = project_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from harp.adapters.driven.storage import (
        dataframe_cache_exists,
        load_dataframe_cache,
        resolve_dataframe_cache_path,
        save_dataframe_cache,
    )
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    runtime_config = load_pipeline_runtime_config()

    return (
        dataframe_cache_exists,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        project_root,
        resolve_dataframe_cache_path,
        runtime_config,
        save_dataframe_cache,
    )


@app.cell
def _(project_root):
    # セル概要: コア層のGLMM関数を読み込む。
    _ = project_root
    from harp.core.modeling.group_condition_glmm import (
        build_group_condition_glmm_model,
        prepare_group_condition_glmm_data,
        sample_group_condition_glmm,
    )

    return (
        build_group_condition_glmm_model,
        prepare_group_condition_glmm_data,
        sample_group_condition_glmm,
    )


@app.cell
def _(mo):
    # セル概要: script実行かinteractive実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, runtime_config):
    # セル概要: 実行設定のデフォルト値を構築する。
    class RunConfig(BaseModel):
        db_url: str = Field(default="")
        start_date: str = Field(default="2019-01-01")
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        row_limit: int = Field(default=200_000)
        cache_enabled_default: bool = Field(default=True)
        refresh_from_db_default: bool = Field(default=False)
        random_seed: int = Field(default=42)
        draws: int = Field(default=400)
        tune: int = Field(default=400)
        chains: int = Field(default=2)
        target_accept: float = Field(default=0.90)

    cfg = RunConfig(db_url=runtime_config.database.db_url)
    return (cfg,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: パラメータ設定セクションの見出しを表示する。
    mo.md("""
    ## 1. 実行パラメータ
    """)
    return


@app.cell
def _(cfg, mo):
    # セル概要: DB設定とサンプリング設定のUIを作る。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)
    race_level_min_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_min, label="Race level min")
    race_level_max_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_max, label="Race level max")
    row_limit_widget = mo.ui.number(start=10_000, stop=2_000_000, step=10_000, value=cfg.row_limit, label="Row limit")
    cache_enabled_widget = mo.ui.switch(value=cfg.cache_enabled_default, label="Use cache")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_from_db_default, label="Force refresh from DB")

    outcome_col_widget = mo.ui.text(label="Outcome col", value="is_place")
    odds_col_widget = mo.ui.text(label="Odds col (optional)", value="j_odds_tansho")
    extra_fixed_cols_widget = mo.ui.text(
        label="Extra fixed cols (comma separated, optional)",
        value="pos4_agari_synergy_wavg5_recent",
        full_width=True,
    )
    distance_col_widget = mo.ui.text(label="Distance col", value="distance_m")
    jockey_col_widget = mo.ui.text(label="Jockey col", value="jockey_cd")

    seed_widget = mo.ui.number(start=1, stop=10_000, step=1, value=cfg.random_seed, label="Seed")
    draws_widget = mo.ui.number(start=100, stop=5000, step=100, value=cfg.draws, label="MCMC draws")
    tune_widget = mo.ui.number(start=100, stop=5000, step=100, value=cfg.tune, label="MCMC tune")
    chains_widget = mo.ui.number(start=1, stop=4, step=1, value=cfg.chains, label="Chains")
    target_accept_widget = mo.ui.slider(start=0.80, stop=0.99, step=0.01, value=cfg.target_accept, label="target_accept")

    run_button = mo.ui.run_button(label="Run MCMC")

    mo.vstack(
        [
            mo.md("dbtモデル `mart.m_train_race_horse_past5` からDB読み込みします。"),
            db_url_widget,
            mo.hstack([start_date_widget, race_level_min_widget, race_level_max_widget]),
            mo.hstack([row_limit_widget, cache_enabled_widget, refresh_db_widget]),
            mo.hstack([outcome_col_widget, odds_col_widget, distance_col_widget, jockey_col_widget]),
            extra_fixed_cols_widget,
            mo.hstack([seed_widget, draws_widget, tune_widget, chains_widget, target_accept_widget]),
            run_button,
        ]
    )
    return (
        cache_enabled_widget,
        chains_widget,
        db_url_widget,
        distance_col_widget,
        draws_widget,
        extra_fixed_cols_widget,
        jockey_col_widget,
        odds_col_widget,
        outcome_col_widget,
        race_level_max_widget,
        race_level_min_widget,
        refresh_db_widget,
        row_limit_widget,
        run_button,
        seed_widget,
        start_date_widget,
        target_accept_widget,
        tune_widget,
    )


@app.cell
def _(
    cache_enabled_widget,
    cfg,
    db_url_widget,
    is_script_mode,
    race_level_max_widget,
    race_level_min_widget,
    refresh_db_widget,
    row_limit_widget,
    start_date_widget,
):
    # セル概要: 実行時の設定値を解決し妥当性チェックする。
    if is_script_mode:
        resolved_db_url = cfg.db_url.strip()
        resolved_start_date = cfg.start_date
        resolved_race_level_min = int(cfg.race_level_min)
        resolved_race_level_max = int(cfg.race_level_max)
        resolved_row_limit = int(cfg.row_limit)
        resolved_cache_enabled = bool(cfg.cache_enabled_default)
        resolved_refresh_db = bool(cfg.refresh_from_db_default)
    else:
        resolved_db_url = str(db_url_widget.value).strip()
        resolved_start_date = str(start_date_widget.value).strip()
        resolved_race_level_min = int(race_level_min_widget.value)
        resolved_race_level_max = int(race_level_max_widget.value)
        resolved_row_limit = int(row_limit_widget.value)
        resolved_cache_enabled = bool(cache_enabled_widget.value)
        resolved_refresh_db = bool(refresh_db_widget.value)

    if not resolved_db_url:
        raise ValueError("HARP_DB_URL is required. Set env var or fill text input.")
    if resolved_race_level_min > resolved_race_level_max:
        raise ValueError("race_level_min must be <= race_level_max")
    if resolved_row_limit <= 0:
        raise ValueError("row_limit must be positive")
    return (
        resolved_cache_enabled,
        resolved_db_url,
        resolved_race_level_max,
        resolved_race_level_min,
        resolved_refresh_db,
        resolved_row_limit,
        resolved_start_date,
    )


@app.cell
def _(notebook_analysis_cache_dir):
    # セル概要: DB取得結果のキャッシュパスを作成する。
    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "jockey_distance_glmm_m_train_race_horse_past5.parquet"
    return (cache_path,)


@app.cell
def _(
    cache_path,
    create_engine,
    dataframe_cache_exists,
    load_dataframe_cache,
    pd,
    resolve_dataframe_cache_path,
    resolved_cache_enabled,
    resolved_db_url,
    resolved_race_level_max,
    resolved_race_level_min,
    resolved_refresh_db,
    resolved_row_limit,
    resolved_start_date,
    text,
):
    # セル概要: dbt martテーブルからデータを取得し必要最小列で整形する。
    use_cache = (
        resolved_cache_enabled
        and dataframe_cache_exists(cache_path)
        and (not resolved_refresh_db)
    )
    if use_cache:
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading from {cache_source_path}")
        df_raw = load_dataframe_cache(cache_path)
    else:
        print("[db] querying mart.m_train_race_horse_past5 ...")
        engine = create_engine(resolved_db_url)
        sql = text(
            """
            SELECT
              race_id,
              held_date,
              race_level,
              is_win,
              is_place,
              j_odds_tansho,
              odds_tansho,
              distance_m,
              jockey_cd,
              pos4_agari_synergy_wavg5_recent
            FROM mart.m_train_race_horse_past5
            WHERE held_date >= :start_date
              AND race_level BETWEEN :race_level_min AND :race_level_max
              AND jockey_cd IS NOT NULL
            ORDER BY held_date, race_id
            LIMIT :row_limit
            """
        )
        with engine.connect().execution_options(stream_results=True) as conn:
            df_raw = pd.read_sql_query(
                sql,
                conn,
                params={
                    "start_date": resolved_start_date,
                    "race_level_min": int(resolved_race_level_min),
                    "race_level_max": int(resolved_race_level_max),
                    "row_limit": int(resolved_row_limit),
                },
            )

        if resolved_cache_enabled:
            save_dataframe_cache(df_raw, cache_path)
            print(f"[cache] saved to {cache_path}")

    if df_raw.empty:
        raise ValueError("DB query returned 0 rows. Check filters or source data.")
    return (df_raw,)


@app.cell
def _(df_raw, mo):
    # セル概要: 入力データの先頭行と件数を確認する。
    mo.vstack(
        [
            mo.md("Data source: `dbt mart.m_train_race_horse_past5`") ,
            mo.md(f"Rows: `{len(df_raw):,}`"),
            df_raw.head(8),
        ]
    )
    return


@app.cell
def _(
    df_raw,
    distance_col_widget,
    extra_fixed_cols_widget,
    jockey_col_widget,
    odds_col_widget,
    outcome_col_widget,
    prepare_group_condition_glmm_data,
):
    # セル概要: GLMM向けの数値配列に前処理する。
    odds_col_value = str(odds_col_widget.value).strip()
    extra_fixed_effect_cols = [
        col.strip()
        for col in str(extra_fixed_cols_widget.value).split(",")
        if col.strip()
    ]
    glmm_data = prepare_group_condition_glmm_data(
        df_raw,
        outcome_col=str(outcome_col_widget.value).strip(),
        group_col=str(jockey_col_widget.value).strip(),
        condition_col=str(distance_col_widget.value).strip(),
        odds_col=odds_col_value if odds_col_value else None,
        extra_fixed_effect_cols=extra_fixed_effect_cols,
        center_condition=True,
        scale_condition=True,
    )
    return (glmm_data,)


@app.cell
def _(glmm_data, mo):
    # セル概要: 前処理後データの統計量を表示する。
    mo.md(
        "\n".join(
            [
                "### Design Matrix Stats",
                f"- n_obs: `{glmm_data.n_obs}`",
                f"- n_groups: `{glmm_data.n_groups}`",
                f"- condition_center: `{glmm_data.condition_center:.4f}`",
                f"- condition_scale: `{glmm_data.condition_scale:.4f}`",
            ]
        )
    )
    return


@app.cell
def _(build_group_condition_glmm_model, glmm_data):
    # セル概要: PyMCのGLMMモデルオブジェクトを構築する。
    model = build_group_condition_glmm_model(glmm_data)
    return (model,)


@app.cell
def _(
    chains_widget,
    draws_widget,
    is_script_mode,
    model,
    run_button,
    sample_group_condition_glmm,
    seed_widget,
    target_accept_widget,
    tune_widget,
):
    # セル概要: script時は自動、interactive時はボタンでMCMCを実行する。
    should_run = is_script_mode or bool(run_button.value)
    if should_run:
        idata = sample_group_condition_glmm(
            model,
            draws=int(draws_widget.value),
            tune=int(tune_widget.value),
            chains=int(chains_widget.value),
            cores=1,
            target_accept=float(target_accept_widget.value),
            random_seed=int(seed_widget.value),
            progressbar=not is_script_mode,
        )
        sample_status = "sampled"
    else:
        idata = None
        sample_status = "waiting_for_run_button"
    return idata, sample_status, should_run


@app.cell
def _(mo, sample_status):
    # セル概要: サンプリング状態を表示する。
    message = "Sampling completed." if sample_status == "sampled" else "Press `Run MCMC` to start sampling."
    mo.md(message)
    return


@app.cell
def _(az, idata, mo, pd, should_run):
    # セル概要: 固定効果と分散パラメータの要約統計を表示する。
    if not should_run or idata is None:
        summary_df = pd.DataFrame()
        summary_view = mo.md("Posterior summary is not available yet.")
    else:
        preferred_var_names = [
            "beta0",
            "beta_log_odds",
            "beta_condition",
            "sigma_group",
            "sigma_group_condition",
        ]
        posterior_names = set(idata.posterior.data_vars.keys())
        summary_var_names = [
            name for name in preferred_var_names if name in posterior_names
        ]
        summary_df = az.summary(
            idata,
            var_names=summary_var_names,
            kind="stats",
        )
        summary_view = summary_df
    summary_view
    return


@app.cell
def _(glmm_data, idata, mo, pd, should_run):
    # セル概要: 主体ごとの条件傾き事後平均ランキングを表示する。
    if not should_run or idata is None:
        ranking = pd.DataFrame()
        ranking_view = mo.md("Group ranking is not available yet.")
    else:
        slope_mean = (
            idata.posterior["group_condition"]
            .mean(dim=("chain", "draw"))
            .to_numpy()
            .reshape(-1)
        )
        intercept_mean = (
            idata.posterior["group_intercept"]
            .mean(dim=("chain", "draw"))
            .to_numpy()
            .reshape(-1)
        )
        ranking = pd.DataFrame(
            {
                "group": list(glmm_data.group_codes),
                "distance_slope_mean": slope_mean,
                "intercept_mean": intercept_mean,
            }
        ).sort_values("distance_slope_mean", ascending=False, ignore_index=True)
        ranking_view = mo.vstack([mo.md("### Condition slope posterior mean"), ranking.head(15)])
    ranking_view
    return


if __name__ == "__main__":
    app.run()
