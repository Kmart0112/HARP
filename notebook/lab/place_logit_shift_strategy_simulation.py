import marimo

__generated_with = "0.22.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebook で使う依存ライブラリを読み込む。
    import os
    import random
    import shlex
    import sys
    from pathlib import Path

    import lightgbm as lgb
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel, Field
    from sklearn.calibration import calibration_curve

    return (
        BaseModel,
        Field,
        Path,
        calibration_curve,
        lgb,
        mo,
        np,
        os,
        pd,
        plt,
        random,
        shlex,
        sys,
    )


@app.cell
def _(mo):
    # セル概要: notebook のタイトルと狙いを表示する。
    mo.md(
        "\n".join(
            [
                "# Place Logit Shift Strategy Simulation",
                "",
                "- train / test split で LightGBM + Platt を学習する",
                "- test 年の `p_place_raw` と `p_place_platt` に race-level `logit shift` をかける",
                "- `raw / raw_shift / platt / platt_shift` の買い方シミュレーションを比較する",
                "- script mode ではそのまま最後まで走り、CSV を `notebook/lab/tmp/place_logit_shift_strategy` に保存する",
            ]
        )
    )
    return


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトパスと共通 helper を解決する。
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "lab"
    OUTPUT_DIR = NOTEBOOK_ROOT / "tmp" / "place_logit_shift_strategy"

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from harp.controllers import (
        NotebookFeatureConfigController,
        build_notebook_config,
    )
    from pipeline.runtime_settings import load_pipeline_runtime_config
    from harp.shared.paths import notebook_analysis_cache_dir

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    notebook_feature_config = NotebookFeatureConfigController(load_pipeline_runtime_config())
    return (
        OUTPUT_DIR,
        build_notebook_config,
        notebook_analysis_cache_dir,
        notebook_feature_config,
    )


@app.cell
def _(mo):
    # セル概要: script 実行か interactive 実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, OUTPUT_DIR, notebook_feature_config):
    # セル概要: notebook 全体の既定設定を定義する。
    class RunConfig(BaseModel):
        train_year_start: int = Field(default=2013)
        train_year_end: int = Field(default=2024)
        test_year: int = Field(default=2025)
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        main_parquet_path: str = Field(default="")
        odds_parquet_path: str = Field(default="")
        fukusho_type: str = Field(default="j_odds_fukusho_avg")
        global_seed: int = Field(default=42)
        strategy_top_n: int = Field(default=1)
        threshold_min: float = Field(default=0.0)
        threshold_max: float = Field(default=0.30)
        threshold_step: float = Field(default=0.01)
        kelly_edge_th: float = Field(default=0.16)
        kelly_fraction: float = Field(default=0.10)
        initial_bankroll: float = Field(default=1.0)
        block_size: int = Field(default=30)
        max_bets_per_race: int = Field(default=2)
        per_bet_max_frac: float = Field(default=0.05)
        output_dir: str = Field(default=str(OUTPUT_DIR))

    cfg = RunConfig()
    return RunConfig, cfg


@app.cell
def _(cfg, mo):
    # セル概要: notebook の設定 UI を表示する。
    feature_set_name_widget = mo.ui.text(
        label="Feature set name",
        value=cfg.feature_set_name,
        full_width=True,
    )
    registry_path_widget = mo.ui.text(
        label="Registry path",
        value=cfg.registry_path,
        full_width=True,
    )
    main_parquet_path_widget = mo.ui.text(
        label="Main parquet path",
        value=cfg.main_parquet_path,
        placeholder="notebook/tmp/analysis_cache/....parquet",
        full_width=True,
    )
    odds_parquet_path_widget = mo.ui.text(
        label="Odds parquet path",
        value=cfg.odds_parquet_path,
        placeholder="notebook/tmp/analysis_cache/race_odds.parquet",
        full_width=True,
    )
    fukusho_type_widget = mo.ui.dropdown(
        options=[
            "j_odds_fukusho_avg",
            "j_odds_fukusho_high",
            "j_odds_fukusho_low",
            "odds_fukusho_avg",
            "odds_fukusho_high",
            "odds_fukusho_low",
        ],
        value=cfg.fukusho_type,
        label="Simulation odds column",
    )
    strategy_top_n_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.strategy_top_n,
        label="Top N per race",
    )
    threshold_min_widget = mo.ui.number(
        start=0.0,
        step=0.01,
        value=cfg.threshold_min,
        label="Threshold min",
    )
    threshold_max_widget = mo.ui.number(
        start=0.01,
        step=0.01,
        value=cfg.threshold_max,
        label="Threshold max",
    )
    threshold_step_widget = mo.ui.number(
        start=0.01,
        step=0.01,
        value=cfg.threshold_step,
        label="Threshold step",
    )
    kelly_edge_th_widget = mo.ui.number(
        start=0.0,
        step=0.01,
        value=cfg.kelly_edge_th,
        label="Kelly edge threshold",
    )
    kelly_fraction_widget = mo.ui.number(
        start=0.01,
        step=0.01,
        value=cfg.kelly_fraction,
        label="Kelly fraction",
    )
    initial_bankroll_widget = mo.ui.number(
        start=0.1,
        step=0.1,
        value=cfg.initial_bankroll,
        label="Initial bankroll",
    )
    block_size_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.block_size,
        label="Kelly block size",
    )
    max_bets_per_race_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.max_bets_per_race,
        label="Kelly max bets / race",
    )
    per_bet_max_frac_widget = mo.ui.number(
        start=0.01,
        step=0.01,
        value=cfg.per_bet_max_frac,
        label="Kelly per-bet cap",
    )

    mo.vstack(
        [
            mo.md("## 1. 実行設定"),
            feature_set_name_widget,
            registry_path_widget,
            main_parquet_path_widget,
            odds_parquet_path_widget,
            mo.hstack([fukusho_type_widget, strategy_top_n_widget]),
            mo.hstack([threshold_min_widget, threshold_max_widget, threshold_step_widget]),
            mo.hstack([kelly_edge_th_widget, kelly_fraction_widget, initial_bankroll_widget]),
            mo.hstack([block_size_widget, max_bets_per_race_widget, per_bet_max_frac_widget]),
            mo.md("しきい値は test 年で最適化されるので、ここで出る ROI は探索用の目安として読む。"),
        ]
    )
    return (
        block_size_widget,
        feature_set_name_widget,
        fukusho_type_widget,
        initial_bankroll_widget,
        kelly_edge_th_widget,
        kelly_fraction_widget,
        main_parquet_path_widget,
        max_bets_per_race_widget,
        odds_parquet_path_widget,
        per_bet_max_frac_widget,
        registry_path_widget,
        strategy_top_n_widget,
        threshold_max_widget,
        threshold_min_widget,
        threshold_step_widget,
    )


@app.cell
def _(
    RunConfig,
    block_size_widget,
    build_notebook_config,
    cfg,
    feature_set_name_widget,
    fukusho_type_widget,
    initial_bankroll_widget,
    is_script_mode,
    kelly_edge_th_widget,
    kelly_fraction_widget,
    main_parquet_path_widget,
    max_bets_per_race_widget,
    mo,
    notebook_analysis_cache_dir,
    odds_parquet_path_widget,
    per_bet_max_frac_widget,
    registry_path_widget,
    strategy_top_n_widget,
    threshold_max_widget,
    threshold_min_widget,
    threshold_step_widget,
):
    # セル概要: UI / CLI を統合して実行時設定を確定する。
    if is_script_mode:
        resolved_cfg = build_notebook_config(
            RunConfig,
            defaults=cfg,
            cli_args=mo.cli_args(),
        )
    else:
        resolved_cfg = build_notebook_config(
            RunConfig,
            defaults=cfg,
            overrides={
                "block_size": int(block_size_widget.value),
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "fukusho_type": str(fukusho_type_widget.value).strip(),
                "initial_bankroll": float(initial_bankroll_widget.value),
                "kelly_edge_th": float(kelly_edge_th_widget.value),
                "kelly_fraction": float(kelly_fraction_widget.value),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "max_bets_per_race": int(max_bets_per_race_widget.value),
                "odds_parquet_path": str(odds_parquet_path_widget.value).strip(),
                "per_bet_max_frac": float(per_bet_max_frac_widget.value),
                "registry_path": str(registry_path_widget.value).strip(),
                "strategy_top_n": int(strategy_top_n_widget.value),
                "threshold_max": float(threshold_max_widget.value),
                "threshold_min": float(threshold_min_widget.value),
                "threshold_step": float(threshold_step_widget.value),
            },
        )

    cache_dir = notebook_analysis_cache_dir()
    default_main = cache_dir / (
        f"m_train_race_horse_past5_{int(resolved_cfg.train_year_start)}_{int(resolved_cfg.test_year)}.parquet"
    )
    default_odds = cache_dir / "race_odds.parquet"
    resolved_cfg = resolved_cfg.model_copy(
        update={
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip() or str(default_main),
            "odds_parquet_path": str(resolved_cfg.odds_parquet_path).strip() or str(default_odds),
            "registry_path": str(resolved_cfg.registry_path).strip(),
        }
    )

    if float(resolved_cfg.threshold_step) <= 0.0:
        raise ValueError("threshold_step must be positive.")
    if float(resolved_cfg.threshold_max) < float(resolved_cfg.threshold_min):
        raise ValueError("threshold_max must be >= threshold_min.")
    return (resolved_cfg,)


@app.cell
def _(np, os, random, resolved_cfg):
    # セル概要: 乱数 seed を固定する。
    os.environ["PYTHONHASHSEED"] = str(int(resolved_cfg.global_seed))
    random.seed(int(resolved_cfg.global_seed))
    np.random.seed(int(resolved_cfg.global_seed))
    return


@app.cell
def _(mo, resolved_cfg):
    # セル概要: 確定した設定を表示する。
    mo.md(
        "\n".join(
            [
                "## 2. 実行設定（確定値）",
                f"- train years: `{resolved_cfg.train_year_start}` - `{resolved_cfg.train_year_end}`",
                f"- test year: `{resolved_cfg.test_year}`",
                f"- main parquet: `{resolved_cfg.main_parquet_path}`",
                f"- odds parquet: `{resolved_cfg.odds_parquet_path}`",
                f"- fukusho odds: `{resolved_cfg.fukusho_type}`",
            ]
        )
    )
    return


@app.cell
def _(pd, resolved_cfg):
    # セル概要: 学習用 parquet を読み込む。
    main_path = resolved_cfg.main_parquet_path
    df_main = pd.read_parquet(main_path)
    df_main.head(1)
    return (df_main,)


@app.cell
def _(Path, pd, resolved_cfg, shlex):
    # セル概要: オッズ parquet を読み込む。
    odds_path = Path(resolved_cfg.odds_parquet_path)
    if not odds_path.exists():
        export_cmd = " ".join(
            [
                "scripts/refresh_analysis_cache.sh",
                "--skip-dbt",
                "--train-year-start",
                str(resolved_cfg.train_year_start),
                "--test-year",
                str(resolved_cfg.test_year),
                "--odds-output",
                shlex.quote(str(odds_path)),
            ]
        )
        raise ValueError(
            "Odds parquet not found.\n"
            f"missing_path={odds_path}\n"
            f"run_command={export_cmd}"
        )

    df_odds = pd.read_parquet(odds_path)
    df_odds.head(1)
    return (df_odds,)


@app.cell
def _(mo):
    # セル概要: 学習データ作成セクションの見出しを表示する。
    mo.md("""
    ## 3. 学習データ作成
    """)
    return


@app.cell
def _(df_main, notebook_feature_config, pd, resolved_cfg):
    # セル概要: feature set を解決して dataset 作成に必要な列を確定する。
    from harp.core.training import build_binary_dataset

    _, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
    )

    df_feat = df_main.copy()
    held_dt = pd.to_datetime(df_feat["held_date"], errors="coerce")
    if held_dt.isna().any():
        raise ValueError(f"held_date conversion failed: {int(held_dt.isna().sum())} rows")
    df_feat["held_year"] = held_dt.dt.year.astype("int64")

    ds = build_binary_dataset(
        df=df_feat,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_place",
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        test_year=int(resolved_cfg.test_year),
    )
    return df_feat, ds


@app.cell
def _(ds, mo):
    # セル概要: split サイズを表示する。
    mo.md(
        "\n".join(
            [
                "train / val / test split",
                f"- train: `{ds.X_tr.shape}`",
                f"- val: `{ds.X_val.shape}`",
                f"- test: `{ds.X_test.shape}`",
                f"- test rows: `{len(ds.X_test)}`",
            ]
        )
    )
    return


@app.cell
def _(mo):
    # セル概要: モデル学習セクションの見出しを表示する。
    mo.md("""
    ## 4. Base model 学習
    """)
    return


@app.cell
def _(ds, lgb, resolved_cfg):
    # セル概要: LightGBM を学習する。
    from harp.core.training import train_binary_lgbm

    model_params = {
        "objective": "binary",
        "n_estimators": 4000,
        "learning_rate": 0.03,
        "num_leaves": 15,
        "max_depth": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.6,
        "min_child_samples": 200,
        "min_split_gain": 0.01,
        "reg_alpha": 0.0,
        "reg_lambda": 0.0,
        "random_state": int(resolved_cfg.global_seed),
        "bagging_seed": int(resolved_cfg.global_seed),
        "feature_fraction_seed": int(resolved_cfg.global_seed),
        "data_random_seed": int(resolved_cfg.global_seed),
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": -1,
    }
    fit_kwargs = {
        "eval_set": [(ds.X_val, ds.y_val)],
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(200, verbose=True),
            lgb.log_evaluation(period=50),
        ],
    }
    result = train_binary_lgbm(ds=ds, model_params=model_params, fit_kwargs=fit_kwargs)
    return (result,)


@app.cell
def _(mo, result):
    # セル概要: base model の validation metrics を表示する。
    metrics = result.metrics
    mo.md(
        "\n".join(
            [
                "validation metrics",
                f"- AUC: `{metrics.get('auc')}`",
                f"- Brier: `{metrics.get('brier')}`",
                f"- LogLoss: `{metrics.get('logloss')}`",
            ]
        )
    )
    return


@app.cell
def _(mo):
    # セル概要: test 予測作成セクションの見出しを表示する。
    mo.md("""
    ## 5. Test 年予測 + odds 結合
    """)
    return


@app.cell
def _(df_feat, df_odds, ds, pd, resolved_cfg, result):
    # セル概要: test 年の base 確率と複勝オッズ・払戻を結合する。
    pred_test = result.model.predict_proba(ds.X_test)[:, 1].astype(float)

    test_idx = ds.X_test.index.to_numpy()
    df_test = df_feat.loc[test_idx, ["race_id", "horse_number", "held_date", "horse_name"]].copy()
    df_test["race_id"] = df_test["race_id"].astype(str)
    df_test["horse_number"] = pd.to_numeric(df_test["horse_number"], errors="raise").astype(int)
    df_test["y_true"] = ds.y_test.astype(int).values
    df_test["p_place_raw"] = pred_test

    odds_cols = [
        "race_id",
        "horse_number",
        "pay_fukusho",
        "odds_fukusho_low",
        "odds_fukusho_high",
        "odds_fukusho_avg",
        "j_odds_fukusho_low",
        "j_odds_fukusho_high",
        "j_odds_fukusho_avg",
        "j_odds_tansho",
    ]
    missing_odds_cols = [col for col in odds_cols if col not in df_odds.columns]
    if missing_odds_cols:
        raise KeyError(f"race_odds missing columns: {missing_odds_cols}")

    odds_use = df_odds[odds_cols].copy()
    odds_use["race_id"] = odds_use["race_id"].astype(str)
    odds_use["horse_number"] = pd.to_numeric(odds_use["horse_number"], errors="raise").astype(int)
    df_eval_raw = df_test.merge(odds_use, on=["race_id", "horse_number"], how="left")

    odds_candidates = [
        str(resolved_cfg.fukusho_type),
        "j_odds_fukusho_avg",
        "odds_fukusho_avg",
    ]
    odds_col = next((col for col in odds_candidates if col in df_eval_raw.columns), None)
    if odds_col is None:
        raise KeyError(f"missing fukusho odds column. candidates={odds_candidates}")

    df_eval_raw["odds"] = pd.to_numeric(df_eval_raw[odds_col], errors="coerce").astype(float)
    df_eval_raw = df_eval_raw.dropna(subset=["odds"]).copy()
    df_eval_raw["real_return_actual"] = (
        pd.to_numeric(df_eval_raw["pay_fukusho"], errors="coerce").fillna(0.0).astype(float) / 100.0
    )
    df_eval_raw["real_return"] = df_eval_raw["real_return_actual"]
    df_eval_raw["real_profit"] = df_eval_raw["real_return"] - 1.0
    return (df_eval_raw,)


@app.cell
def _(mo):
    # セル概要: Platt 校正セクションの見出しを表示する。
    mo.md("""
    ## 6. Platt 校正 + logit shift
    """)
    return


@app.cell
def _(OUTPUT_DIR, df_eval_raw, df_feat, ds, pd, resolved_cfg, result):
    # セル概要: train OOF で Platt 校正器を学習し、test 年へ適用する。
    from harp.core.training import apply_platt_logodds, fit_platt_logodds_oof

    platt_odds_candidates = [
        "j_odds_tansho",
        "j_odds_fukusho_avg",
        str(resolved_cfg.fukusho_type),
        "odds_fukusho_avg",
    ]
    platt_odds_col = next((col for col in platt_odds_candidates if col in df_feat.columns), None)
    if platt_odds_col is None:
        raise KeyError(f"missing platt odds column in df_feat. candidates={platt_odds_candidates}")

    platt_info = fit_platt_logodds_oof(
        model=result.model,
        ds=ds,
        df_meta=df_feat,
        odds_col=platt_odds_col,
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        valid_years_back=5,
        eps=1e-12,
    )

    payload = {
        "calibration": {
            "method": "platt_logodds",
            "params": platt_info,
        }
    }
    p_base = (
        pd.to_numeric(df_eval_raw["p_place_raw"], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .clip(0.0, 1.0)
    )
    df_eval = df_eval_raw.copy()
    df_eval["p_place_platt"] = apply_platt_logodds(
        base_proba=p_base.to_numpy(),
        payload=payload,
        df_feat=df_eval,
        odds_col=platt_odds_col if platt_odds_col in df_eval.columns else None,
    )

    fold_metrics_path = OUTPUT_DIR / "platt_oof_fold_metrics.csv"
    pd.DataFrame(platt_info.get("fold_metrics", [])).to_csv(fold_metrics_path, index=False)
    print(f"saved platt OOF fold metrics: {fold_metrics_path.resolve()}")
    return (df_eval,)


@app.cell
def _(df_eval, np):
    # セル概要: race ごとの複勝枠数ルールを計算する。
    work = df_eval.copy()
    work["horse_count"] = work.groupby("race_id", dropna=False)["race_id"].transform("size").astype(int)
    work["k_rule"] = np.where(work["horse_count"] <= 7, 2.0, 3.0)
    work["k_rule"] = np.minimum(work["k_rule"], work["horse_count"].astype(float))
    work["k_actual"] = work.groupby("race_id", dropna=False)["y_true"].transform("sum").astype(float)
    return (work,)


@app.cell
def _(OUTPUT_DIR, np, pd, work):
    # セル概要: raw / Platt 後確率に race-level logit shift をかける。
    from harp.core.training import apply_logit_shift_grouped

    k_by_group = (
        work.groupby("race_id", dropna=False)["k_rule"]
        .first()
        .astype(float)
        .to_dict()
    )
    p_raw_shift, lambda_by_race_raw = apply_logit_shift_grouped(
        work["p_place_raw"].to_numpy(dtype=float),
        work["race_id"].to_numpy(dtype=object),
        k_by_group=k_by_group,
        return_lambda=True,
    )
    p_platt_shift, lambda_by_race_platt = apply_logit_shift_grouped(
        work["p_place_platt"].to_numpy(dtype=float),
        work["race_id"].to_numpy(dtype=object),
        k_by_group=k_by_group,
        return_lambda=True,
    )

    df_eval_shift = work.copy()
    df_eval_shift["p_place_raw_shift"] = np.asarray(p_raw_shift, dtype=float)
    df_eval_shift["p_place_platt_shift"] = np.asarray(p_platt_shift, dtype=float)

    lambda_path = OUTPUT_DIR / "logit_shift_lambda_by_race.csv"
    pd.DataFrame(
        {
            "race_id": list(lambda_by_race_raw.keys()),
            "lambda_raw_shift": list(lambda_by_race_raw.values()),
            "lambda_platt_shift": [lambda_by_race_platt[race_id] for race_id in lambda_by_race_raw],
        }
    ).sort_values("race_id").to_csv(lambda_path, index=False)
    print(f"saved logit shift lambdas: {lambda_path.resolve()}")
    return (df_eval_shift,)


@app.cell
def _(calibration_curve, np, pd):
    # セル概要: overall / odds帯別の reliability・curve helper を定義する。
    def build_reliability_table(
        df: pd.DataFrame,
        *,
        prob_col: str,
        label_col: str = "y_true",
        n_bins: int = 10,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        work = df[[prob_col, label_col]].dropna().copy()
        if work.empty:
            return pd.DataFrame(), pd.DataFrame()
        work[prob_col] = pd.to_numeric(work[prob_col], errors="coerce").clip(0.0, 1.0)
        work[label_col] = pd.to_numeric(work[label_col], errors="coerce").fillna(0).astype(int)
        work = work.dropna(subset=[prob_col]).copy()
        if work.empty:
            return pd.DataFrame(), pd.DataFrame()

        q_bins = min(n_bins, int(work[prob_col].nunique()))
        if q_bins <= 1:
            work["decile"] = 0
            prob_true = np.array([float(work[label_col].mean())], dtype=float)
            prob_pred = np.array([float(work[prob_col].mean())], dtype=float)
        else:
            work["decile"] = pd.qcut(work[prob_col], q=q_bins, labels=False, duplicates="drop")
            prob_true, prob_pred = calibration_curve(
                work[label_col].values,
                work[prob_col].values,
                n_bins=q_bins,
                strategy="quantile",
            )

        summary = (
            work.groupby("decile", dropna=False)
            .agg(
                n=(label_col, "size"),
                p_mean=(prob_col, "mean"),
                y_rate=(label_col, "mean"),
                p_min=(prob_col, "min"),
                p_max=(prob_col, "max"),
            )
            .reset_index()
            .sort_values("decile")
        )
        summary["gap"] = summary["y_rate"] - summary["p_mean"]
        curve = pd.DataFrame({"prob_pred": prob_pred, "prob_true": prob_true})
        return summary, curve

    def _attach_odds_band(
        df: pd.DataFrame,
        odds_col: str = "odds",
    ) -> pd.DataFrame:
        from harp.core.inference.edge_simulation import DEFAULT_ODDS_BINS, DEFAULT_ODDS_LABELS

        work = df.copy()
        if work.empty:
            return pd.DataFrame()
        work[odds_col] = pd.to_numeric(work[odds_col], errors="coerce")
        work = work.dropna(subset=[odds_col]).copy()
        if work.empty:
            return pd.DataFrame()

        bins = [0.0, *list(DEFAULT_ODDS_BINS)]
        labels = ["<=1.1", *list(DEFAULT_ODDS_LABELS)]
        work["odds_band"] = pd.cut(
            work[odds_col],
            bins=bins,
            labels=labels,
            include_lowest=True,
            right=True,
        )
        work = work.dropna(subset=["odds_band"]).copy()
        return work

    def build_odds_band_reliability_table(
        df: pd.DataFrame,
        *,
        prob_col: str,
        odds_col: str = "odds",
        label_col: str = "y_true",
    ) -> pd.DataFrame:
        work = _attach_odds_band(df, odds_col=odds_col)
        if work.empty:
            return pd.DataFrame()

        work[prob_col] = pd.to_numeric(work[prob_col], errors="coerce").clip(0.0, 1.0)
        work[label_col] = pd.to_numeric(work[label_col], errors="coerce").fillna(0).astype(int)
        work = work.dropna(subset=[prob_col]).copy()
        if work.empty:
            return pd.DataFrame()

        summary = (
            work.groupby("odds_band", observed=False, dropna=False)
            .agg(
                n=(label_col, "size"),
                odds_mean=(odds_col, "mean"),
                odds_min=(odds_col, "min"),
                odds_max=(odds_col, "max"),
                p_mean=(prob_col, "mean"),
                y_rate=(label_col, "mean"),
            )
            .reset_index()
        )
        summary["odds_band"] = summary["odds_band"].astype(str)
        summary["gap"] = summary["y_rate"] - summary["p_mean"]
        summary["abs_gap"] = summary["gap"].abs()
        return summary[summary["n"] > 0].reset_index(drop=True)

    def build_odds_band_curve_table(
        df: pd.DataFrame,
        *,
        prob_col: str,
        odds_col: str = "odds",
        label_col: str = "y_true",
        n_bins: int = 6,
        min_rows_per_band: int = 40,
    ) -> pd.DataFrame:
        work = _attach_odds_band(df, odds_col=odds_col)
        if work.empty:
            return pd.DataFrame()

        work[prob_col] = pd.to_numeric(work[prob_col], errors="coerce").clip(0.0, 1.0)
        work[label_col] = pd.to_numeric(work[label_col], errors="coerce").fillna(0).astype(int)
        work = work.dropna(subset=[prob_col]).copy()
        if work.empty:
            return pd.DataFrame()

        curve_parts: list[pd.DataFrame] = []
        for odds_band, part in work.groupby("odds_band", observed=False, dropna=False):
            if len(part) < int(min_rows_per_band):
                continue
            q_bins = min(int(n_bins), int(part[prob_col].nunique()))
            if q_bins <= 1:
                curve_parts.append(
                    pd.DataFrame(
                        {
                            "odds_band": [str(odds_band)],
                            "bin_idx": [0],
                            "prob_pred": [float(part[prob_col].mean())],
                            "prob_true": [float(part[label_col].mean())],
                            "n": [int(len(part))],
                            "p_min": [float(part[prob_col].min())],
                            "p_max": [float(part[prob_col].max())],
                        }
                    )
                )
                continue

            band = part.copy()
            band["bin_idx"] = pd.qcut(
                band[prob_col],
                q=q_bins,
                labels=False,
                duplicates="drop",
            )
            curve = (
                band.groupby("bin_idx", dropna=False)
                .agg(
                    n=(label_col, "size"),
                    prob_pred=(prob_col, "mean"),
                    prob_true=(label_col, "mean"),
                    p_min=(prob_col, "min"),
                    p_max=(prob_col, "max"),
                )
                .reset_index()
            )
            curve.insert(0, "odds_band", str(odds_band))
            curve_parts.append(curve)

        if not curve_parts:
            return pd.DataFrame()
        return pd.concat(curve_parts, ignore_index=True)

    return (
        build_odds_band_curve_table,
        build_odds_band_reliability_table,
        build_reliability_table,
    )


@app.cell
def _(
    OUTPUT_DIR,
    build_odds_band_curve_table,
    build_odds_band_reliability_table,
    build_reliability_table,
    df_eval_shift,
    np,
    pd,
):
    # セル概要: variant ごとの metrics と overall / odds帯別 reliability / curve を集計する。
    from harp.core.training.metrics import calc_binary_metrics

    _variant_specs = [
        ("raw", "p_place_raw"),
        ("raw_shift", "p_place_raw_shift"),
        ("platt", "p_place_platt"),
        ("platt_shift", "p_place_platt_shift"),
    ]
    race_base = (
        df_eval_shift.groupby("race_id", dropna=False)
        .agg(
            k_rule=("k_rule", "first"),
            k_actual=("k_actual", "first"),
            raw_sum=("p_place_raw", "sum"),
            raw_shift_sum=("p_place_raw_shift", "sum"),
            platt_sum=("p_place_platt", "sum"),
            platt_shift_sum=("p_place_platt_shift", "sum"),
        )
        .reset_index()
    )

    metric_rows: list[dict[str, float | str]] = []
    reliability_frames: list[pd.DataFrame] = []
    curve_frames: list[pd.DataFrame] = []
    odds_band_frames: list[pd.DataFrame] = []
    odds_band_curve_frames: list[pd.DataFrame] = []
    for _variant_name, _prob_col in _variant_specs:
        metric = calc_binary_metrics(
            df_eval_shift["y_true"],
            df_eval_shift[_prob_col].to_numpy(dtype=float),
        )
        reliability, curve = build_reliability_table(df_eval_shift, prob_col=_prob_col)
        odds_band_reliability = build_odds_band_reliability_table(df_eval_shift, prob_col=_prob_col)
        odds_band_curve = build_odds_band_curve_table(df_eval_shift, prob_col=_prob_col)
        reliability.insert(0, "variant", _variant_name)
        curve.insert(0, "variant", _variant_name)
        odds_band_reliability.insert(0, "variant", _variant_name)
        odds_band_curve.insert(0, "variant", _variant_name)
        reliability_frames.append(reliability)
        curve_frames.append(curve)
        odds_band_frames.append(odds_band_reliability)
        odds_band_curve_frames.append(odds_band_curve)

        sum_col = {
            "p_place_raw": "raw_sum",
            "p_place_raw_shift": "raw_shift_sum",
            "p_place_platt": "platt_sum",
            "p_place_platt_shift": "platt_shift_sum",
        }[_prob_col]
        metric_rows.append(
            {
                "variant": _variant_name,
                "auc": float(metric["auc"]),
                "brier": float(metric["brier"]),
                "logloss": float(metric["logloss"]),
                "mean_prob": float(df_eval_shift[_prob_col].mean()),
                "mean_y": float(df_eval_shift["y_true"].mean()),
                "race_sum_mae_vs_rule": float((race_base[sum_col] - race_base["k_rule"]).abs().mean()),
                "race_sum_mae_vs_actual": float((race_base[sum_col] - race_base["k_actual"]).abs().mean()),
                "race_sum_rmse_vs_rule": float(
                    np.sqrt(np.mean((race_base[sum_col] - race_base["k_rule"]) ** 2))
                ),
                "race_sum_rmse_vs_actual": float(
                    np.sqrt(np.mean((race_base[sum_col] - race_base["k_actual"]) ** 2))
                ),
            }
        )

    variant_metrics = pd.DataFrame(metric_rows)
    reliability_table = pd.concat(reliability_frames, ignore_index=True)
    calibration_curve_df = pd.concat(curve_frames, ignore_index=True)
    odds_band_reliability = pd.concat(odds_band_frames, ignore_index=True)
    odds_band_curve = pd.concat(odds_band_curve_frames, ignore_index=True)
    odds_band_reliability["weighted_abs_gap"] = odds_band_reliability["abs_gap"] * odds_band_reliability["n"]
    odds_band_summary = (
        odds_band_reliability.groupby("variant", dropna=False)
        .agg(
            total_n=("n", "sum"),
            mean_abs_gap=("abs_gap", "mean"),
            weighted_abs_gap_sum=("weighted_abs_gap", "sum"),
            max_abs_gap=("abs_gap", "max"),
        )
        .reset_index()
    )
    odds_band_summary["weighted_mean_abs_gap"] = (
        odds_band_summary["weighted_abs_gap_sum"] / odds_band_summary["total_n"].clip(lower=1)
    )
    odds_band_summary = odds_band_summary.drop(columns=["weighted_abs_gap_sum"])

    variant_metrics_path = OUTPUT_DIR / "variant_metrics.csv"
    reliability_path = OUTPUT_DIR / "variant_reliability.csv"
    odds_band_reliability_path = OUTPUT_DIR / "variant_odds_band_reliability.csv"
    odds_band_summary_path = OUTPUT_DIR / "variant_odds_band_summary.csv"
    odds_band_curve_path = OUTPUT_DIR / "variant_odds_band_curve.csv"
    variant_metrics.to_csv(variant_metrics_path, index=False)
    reliability_table.to_csv(reliability_path, index=False)
    odds_band_reliability.to_csv(odds_band_reliability_path, index=False)
    odds_band_summary.to_csv(odds_band_summary_path, index=False)
    odds_band_curve.to_csv(odds_band_curve_path, index=False)
    print(f"saved variant metrics: {variant_metrics_path.resolve()}")
    print(f"saved variant reliability: {reliability_path.resolve()}")
    print(f"saved odds-band reliability: {odds_band_reliability_path.resolve()}")
    print(f"saved odds-band summary: {odds_band_summary_path.resolve()}")
    print(f"saved odds-band curve: {odds_band_curve_path.resolve()}")
    return (
        calibration_curve_df,
        odds_band_curve,
        odds_band_reliability,
        odds_band_summary,
        variant_metrics,
    )


@app.cell
def _(mo):
    # セル概要: metrics の読み方を説明する。
    mo.md(
        "\n".join(
            [
                "## 7. 確率評価の見方",
                "- `race_sum_mae_vs_rule` は「複勝枠数ルールに対して各 race の確率合計がどれだけズレたか」を見る",
                "- `raw_shift` と `platt_shift` はここがほぼ 0 になるはず",
                "- AUC / Brier / LogLoss は最終確率で見て、strategy simulation へ流す前段の品質を確認する",
            ]
        )
    )
    return


@app.cell
def _(mo, variant_metrics):
    # セル概要: variant metrics を表で表示する。
    mo.ui.table(variant_metrics)
    return


@app.cell
def _(mo):
    # セル概要: odds帯別 reliability の読み方を説明する。
    mo.md(
        "\n".join(
            [
                "### Odds帯別 calibration の見方",
                "- `gap = 実績複勝率 - 予測平均確率` なので、0 に近いほどその帯で calibration が揃っている",
                "- `abs_gap` はズレの大きさだけを見る。variant 比較ではまずこれを優先して見る",
                "- `weighted_mean_abs_gap` は bet 数の多い帯を重く見た要約で、実運用の体感に近い",
            ]
        )
    )
    return


@app.cell
def _(mo, odds_band_summary):
    # セル概要: odds帯別 calibration の要約を表示する。
    mo.ui.table(odds_band_summary)
    return


@app.cell
def _(mo, odds_band_reliability):
    # セル概要: odds帯別 reliability の詳細表を表示する。
    mo.ui.table(odds_band_reliability)
    return


@app.cell
def _(mo, np, odds_band_reliability, plt):
    # セル概要: odds帯ごとの gap / abs_gap を描画する。
    _plot_df = odds_band_reliability.copy()
    _band_order = _plot_df["odds_band"].drop_duplicates().tolist()
    _x = np.arange(len(_band_order))

    _fig, _axes = plt.subplots(1, 2, figsize=(14.0, 4.8), sharex=True)
    _variants = _plot_df["variant"].drop_duplicates().tolist()
    _width = 0.18 if len(_variants) >= 4 else 0.22

    for _idx, _variant_name in enumerate(_variants):
        _part = (
            _plot_df[_plot_df["variant"] == _variant_name]
            .set_index("odds_band")
            .reindex(_band_order)
            .reset_index()
        )
        _offset = (_idx - (len(_variants) - 1) / 2.0) * _width
        _axes[0].bar(
            _x + _offset,
            _part["abs_gap"].to_numpy(dtype=float),
            width=_width,
            label=str(_variant_name),
        )
        _axes[1].plot(
            _x,
            _part["gap"].to_numpy(dtype=float),
            marker="o",
            label=str(_variant_name),
        )

    _axes[0].set_title("Absolute calibration gap by odds band")
    _axes[0].set_ylabel("abs gap")
    _axes[0].set_xticks(_x)
    _axes[0].set_xticklabels(_band_order, rotation=30, ha="right")
    _axes[0].grid(True, axis="y", linewidth=0.4, alpha=0.4)
    _axes[0].legend()

    _axes[1].axhline(0.0, color="gray", linestyle="--", linewidth=1.0)
    _axes[1].set_title("Signed calibration gap by odds band")
    _axes[1].set_ylabel("gap = observed - predicted")
    _axes[1].set_xticks(_x)
    _axes[1].set_xticklabels(_band_order, rotation=30, ha="right")
    _axes[1].grid(True, linewidth=0.4, alpha=0.4)
    _axes[1].legend()

    mo.vstack(
        [
            mo.md("どの odds 帯で shift が効いたか、逆に悪化した帯がないかをここで確認する。"),
            _fig,
        ]
    )
    return


@app.cell
def _(mo):
    # セル概要: odds帯別 calibration curve の読み方を説明する。
    mo.md(
        "\n".join(
            [
                "### Odds帯別 calibration curve の見方",
                "- 各パネルが 1 つの odds 帯で、その中で手法ごとの calibration curve を重ねている",
                "- 対角線に近いほど、その odds 帯の中で予測確率と実測複勝率が揃っている",
                "- 高確率側だけ浮く、低確率側だけ沈む、といった帯ごとの歪みを見つけやすい",
            ]
        )
    )
    return


@app.cell
def _(mo, odds_band_curve):
    # セル概要: odds帯別 calibration curve の元テーブルを表示する。
    mo.ui.table(odds_band_curve)
    return


@app.cell
def _(mo, np, odds_band_curve, plt):
    # セル概要: odds帯ごとの calibration curve を手法別に比較描画する。
    if odds_band_curve.empty:
        _ui = mo.md("odds帯別 calibration curve を描くためのデータがまだありません。")
    else:
        _band_order_curve = odds_band_curve["odds_band"].drop_duplicates().tolist()
        _n_panels = len(_band_order_curve)
        _n_cols = 3
        _n_rows = int(np.ceil(_n_panels / _n_cols))
        _fig, _axes = plt.subplots(
            _n_rows,
            _n_cols,
            figsize=(4.8 * _n_cols, 3.9 * _n_rows),
            sharex=True,
            sharey=True,
        )
        _axes_flat = np.atleast_1d(_axes).ravel()

        for _ax, _band_name in zip(_axes_flat, _band_order_curve):
            _band_part = odds_band_curve[odds_band_curve["odds_band"] == _band_name].copy()
            for _variant_name_curve, _variant_part in _band_part.groupby("variant", dropna=False):
                _ax.plot(
                    _variant_part["prob_pred"].to_numpy(dtype=float),
                    _variant_part["prob_true"].to_numpy(dtype=float),
                    marker="o",
                    label=str(_variant_name_curve),
                )
            _ax.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", color="gray", linewidth=1.0)
            _ax.set_title(str(_band_name))
            _ax.grid(True, linewidth=0.4, alpha=0.4)

        for _ax in _axes_flat[_n_panels:]:
            _ax.axis("off")

        for _ax in _axes_flat[::_n_cols]:
            _ax.set_ylabel("observed place rate")
        for _ax in _axes_flat[-_n_cols:]:
            _ax.set_xlabel("mean predicted probability")

        _handles, _labels = _axes_flat[0].get_legend_handles_labels()
        if _handles:
            _fig.legend(_handles, _labels, loc="upper center", ncol=min(len(_labels), 4))
        _fig.suptitle("Calibration curve by odds band and probability variant", y=0.98)
        _fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))

        _ui = mo.vstack(
            [
                mo.md("odds帯ごとに、どの手法が対角線へ近いかを横並びで比べる。"),
                _fig,
            ]
        )
    _ui
    return


@app.cell
def _(calibration_curve_df, mo, plt):
    # セル概要: calibration curve を描画する。
    _fig, _ax = plt.subplots(figsize=(6.8, 5.2))
    for _variant_name, _part in calibration_curve_df.groupby("variant", dropna=False):
        _ax.plot(
            _part["prob_pred"].to_numpy(dtype=float),
            _part["prob_true"].to_numpy(dtype=float),
            marker="o",
            label=str(_variant_name),
        )
    _ax.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", color="gray", linewidth=1.0)
    _ax.set_xlabel("mean predicted probability")
    _ax.set_ylabel("observed place rate")
    _ax.set_title("Calibration curve by probability variant")
    _ax.grid(True, linewidth=0.4, alpha=0.4)
    _ax.legend()
    mo.vstack(
        [
            mo.md("shift 後に高確率側の過大評価がどれだけ締まるかを見る。"),
            _fig,
        ]
    )
    return


@app.cell
def _():
    # セル概要: strategy simulation で使う odds 列名を固定する。
    strategy_odds_col = "odds"
    return (strategy_odds_col,)


@app.cell
def _(np, pd, strategy_odds_col):
    # セル概要: Kelly bankroll simulation helper を定義する。
    from harp.core.inference import prepare_edge_frame as _prepare_edge_frame

    def simulate_kelly_block_rebalance(
        df: pd.DataFrame,
        *,
        prob_col: str,
        edge_th: float,
        kelly_fraction: float,
        initial_bankroll: float,
        block_size: int,
        max_bets_per_race: int,
        per_bet_max_frac: float,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        edge_frame = _prepare_edge_frame(
            df,
            prob_col=prob_col,
            odds_col=strategy_odds_col,
            label_col="y_true",
            ev_profit_col="ev_profit",
            realized_payout_col="real_return",
        )
        race_ids = (
            edge_frame[["race_id"]]
            .drop_duplicates("race_id")
            .sort_values(["race_id"], ascending=[True])["race_id"]
            .tolist()
        )

        bankroll = float(initial_bankroll)
        block_base = float(initial_bankroll)
        bet_rows: list[dict[str, float | int | str]] = []
        race_rows: list[dict[str, float | int | str]] = []

        for race_i, race_id in enumerate(race_ids):
            if bankroll <= 0.0:
                break
            if race_i % int(block_size) == 0:
                block_base = bankroll

            race_df = edge_frame[edge_frame["race_id"] == race_id].copy()
            cand = race_df[race_df["edge"].astype(float) >= float(edge_th)].copy()
            if len(cand) == 0:
                race_rows.append(
                    {
                        "race_i": int(race_i),
                        "race_id": str(race_id),
                        "bankroll_before": float(bankroll),
                        "n_bets": 0,
                        "stake": 0.0,
                        "return": 0.0,
                        "profit": 0.0,
                        "bankroll_after": float(bankroll),
                    }
                )
                continue

            cand = (
                cand.sort_values(["edge", "prob"], ascending=[False, False])
                .head(int(max_bets_per_race))
                .reset_index(drop=True)
            )

            payout_plan = cand["payout_mult_plan"].astype(float).to_numpy().clip(min=1e-12)
            prob = cand["prob"].astype(float).to_numpy().clip(min=0.0, max=1.0)
            b = np.clip(payout_plan - 1.0, 1e-12, None)
            f = (prob * payout_plan - 1.0) / b
            f = np.nan_to_num(f, nan=0.0, posinf=0.0, neginf=0.0).clip(min=0.0)

            stake_raw = block_base * float(kelly_fraction) * f
            bankroll_before = bankroll
            bet_cap = bankroll_before * float(per_bet_max_frac)
            stake_raw = np.minimum(stake_raw, bet_cap)
            total_raw = float(np.sum(stake_raw))
            if total_raw > bankroll_before and bankroll_before > 0.0:
                stake = stake_raw * (bankroll_before / total_raw)
            else:
                stake = stake_raw
            stake = np.clip(stake, 0.0, None)

            payout_real = cand["payout_mult_real"].astype(float).to_numpy()
            y = cand["y"].astype(int).to_numpy()
            ret = np.where(y == 1, stake * payout_real, 0.0)
            profit = ret - stake
            race_stake = float(np.sum(stake))
            race_return = float(np.sum(ret))
            race_profit = float(np.sum(profit))
            bankroll = bankroll_before + race_profit

            for idx in range(len(cand)):
                bet_rows.append(
                    {
                        "race_i": int(race_i),
                        "race_id": str(race_id),
                        "stake": float(stake[idx]),
                        "prob": float(prob[idx]),
                        "edge": float(cand.loc[idx, "edge"]),
                        "odds": float(payout_plan[idx]),
                        "y": int(y[idx]),
                        "return": float(ret[idx]),
                        "profit": float(profit[idx]),
                    }
                )

            race_rows.append(
                {
                    "race_i": int(race_i),
                    "race_id": str(race_id),
                    "bankroll_before": float(bankroll_before),
                    "n_bets": int(len(cand)),
                    "stake": race_stake,
                    "return": race_return,
                    "profit": race_profit,
                    "bankroll_after": float(bankroll),
                }
            )

        bet_detail = pd.DataFrame(bet_rows)
        race_curve = pd.DataFrame(race_rows)
        total_stake = float(bet_detail["stake"].sum()) if len(bet_detail) else 0.0
        total_return = float(bet_detail["return"].sum()) if len(bet_detail) else 0.0
        summary = pd.Series(
            {
                "initial_bankroll": float(initial_bankroll),
                "final_bankroll": float(bankroll),
                "bankroll_multiple": (
                    float(bankroll / float(initial_bankroll))
                    if float(initial_bankroll) != 0.0
                    else np.nan
                ),
                "n_races": int(race_curve.shape[0]),
                "n_bets": int(bet_detail.shape[0]),
                "total_stake": total_stake,
                "total_return": total_return,
                "total_profit": float(total_return - total_stake),
                "roi": float(total_return / total_stake) if total_stake > 0.0 else np.nan,
                "hit_rate": float(bet_detail["y"].mean()) if len(bet_detail) else np.nan,
            }
        )
        return race_curve, bet_detail, summary

    return (simulate_kelly_block_rebalance,)


@app.cell
def _(
    OUTPUT_DIR,
    df_eval_shift,
    np,
    pd,
    resolved_cfg,
    simulate_kelly_block_rebalance,
):
    # セル概要: flat / edge-proportional / Kelly の strategy simulation を variant ごとに回す。
    from harp.core.inference import prepare_edge_frame, simulate_edge_thresholds

    thresholds = np.round(
        np.arange(
            float(resolved_cfg.threshold_min),
            float(resolved_cfg.threshold_max) + float(resolved_cfg.threshold_step) / 2.0,
            float(resolved_cfg.threshold_step),
        ),
        4,
    ).tolist()
    _variant_specs = [
        ("raw", "p_place_raw"),
        ("raw_shift", "p_place_raw_shift"),
        ("platt", "p_place_platt"),
        ("platt_shift", "p_place_platt_shift"),
    ]

    flat_summaries: list[pd.DataFrame] = []
    edge_summaries: list[pd.DataFrame] = []
    kelly_summaries: list[pd.Series] = []
    kelly_curves: list[pd.DataFrame] = []

    for _variant_name, _prob_col in _variant_specs:
        edge_frame = prepare_edge_frame(
            df_eval_shift,
            prob_col=_prob_col,
            odds_col="odds",
            label_col="y_true",
            ev_profit_col="ev_profit",
            realized_payout_col="real_return",
        )

        flat_summary, _flat_details = simulate_edge_thresholds(
            edge_frame,
            thresholds=thresholds,
            selection_mode="top_n_per_race",
            top_n=int(resolved_cfg.strategy_top_n),
            stake_mode="flat",
            stake=1.0,
        )
        flat_summary.insert(0, "variant", _variant_name)
        flat_summaries.append(flat_summary)

        edge_summary, _edge_details = simulate_edge_thresholds(
            edge_frame,
            thresholds=thresholds,
            selection_mode="top_n_per_race",
            top_n=int(resolved_cfg.strategy_top_n),
            stake_mode="edge_proportional",
            edge_unit=0.1,
            stake_at_edge_unit=1.0,
        )
        edge_summary.insert(0, "variant", _variant_name)
        edge_summaries.append(edge_summary)

        kelly_curve, _kelly_detail, kelly_summary = simulate_kelly_block_rebalance(
            df_eval_shift,
            prob_col=_prob_col,
            edge_th=float(resolved_cfg.kelly_edge_th),
            kelly_fraction=float(resolved_cfg.kelly_fraction),
            initial_bankroll=float(resolved_cfg.initial_bankroll),
            block_size=int(resolved_cfg.block_size),
            max_bets_per_race=int(resolved_cfg.max_bets_per_race),
            per_bet_max_frac=float(resolved_cfg.per_bet_max_frac),
        )
        kelly_summary = kelly_summary.copy()
        kelly_summary["variant"] = _variant_name
        kelly_summaries.append(kelly_summary)
        kelly_curve.insert(0, "variant", _variant_name)
        kelly_curves.append(kelly_curve)

    strategy_summary_flat = pd.concat(flat_summaries, ignore_index=True)
    strategy_summary_edge = pd.concat(edge_summaries, ignore_index=True)
    kelly_summary_df = pd.DataFrame(kelly_summaries)
    kelly_curve_df = pd.concat(kelly_curves, ignore_index=True)

    strategy_summary_flat.to_csv(OUTPUT_DIR / "strategy_summary_flat.csv", index=False)
    strategy_summary_edge.to_csv(OUTPUT_DIR / "strategy_summary_edge.csv", index=False)
    kelly_summary_df.to_csv(OUTPUT_DIR / "strategy_summary_kelly.csv", index=False)
    kelly_curve_df.to_csv(OUTPUT_DIR / "strategy_kelly_curve.csv", index=False)
    print(f"saved flat strategy summary: {(OUTPUT_DIR / 'strategy_summary_flat.csv').resolve()}")
    print(f"saved edge strategy summary: {(OUTPUT_DIR / 'strategy_summary_edge.csv').resolve()}")
    print(f"saved kelly strategy summary: {(OUTPUT_DIR / 'strategy_summary_kelly.csv').resolve()}")
    print(f"saved kelly race curve: {(OUTPUT_DIR / 'strategy_kelly_curve.csv').resolve()}")
    return (
        kelly_curve_df,
        kelly_summary_df,
        strategy_summary_edge,
        strategy_summary_flat,
    )


@app.cell
def _(mo):
    # セル概要: strategy simulation の読み方を説明する。
    mo.md(
        "\n".join(
            [
                "## 8. 買い方シミュレーションの見方",
                "- `flat` は 1 点固定、`edge_proportional` は edge に比例して賭け金を増やす",
                "- `Kelly` は race 内の上位候補へ資金配分する探索版",
                "- test 年で threshold を見ているので、最大 ROI 行はそのまま本番採用せず候補として扱う",
            ]
        )
    )
    return


@app.cell
def _(mo, strategy_summary_flat):
    # セル概要: flat strategy summary を表示する。
    mo.ui.table(strategy_summary_flat)
    return


@app.cell
def _(mo, strategy_summary_edge):
    # セル概要: edge-proportional strategy summary を表示する。
    mo.ui.table(strategy_summary_edge)
    return


@app.cell
def _(kelly_summary_df, mo):
    # セル概要: Kelly summary を表示する。
    mo.ui.table(kelly_summary_df)
    return


@app.cell
def _(mo, plt, strategy_summary_edge, strategy_summary_flat):
    # セル概要: threshold ごとの ROI を描画する。
    _fig, _axes = plt.subplots(1, 2, figsize=(13.0, 4.8), sharex=True)
    for _variant_name, _part in strategy_summary_flat.groupby("variant", dropna=False):
        _axes[0].plot(
            _part["threshold"].to_numpy(dtype=float),
            _part["roi"].to_numpy(dtype=float),
            marker="o",
            label=str(_variant_name),
        )
    _axes[0].axhline(1.0, color="gray", linestyle="--", linewidth=1.0)
    _axes[0].set_title("Flat stake ROI")
    _axes[0].set_xlabel("edge threshold")
    _axes[0].set_ylabel("ROI")
    _axes[0].grid(True, linewidth=0.4, alpha=0.4)
    _axes[0].legend()

    for _variant_name, _part in strategy_summary_edge.groupby("variant", dropna=False):
        _axes[1].plot(
            _part["threshold"].to_numpy(dtype=float),
            _part["roi"].to_numpy(dtype=float),
            marker="o",
            label=str(_variant_name),
        )
    _axes[1].axhline(1.0, color="gray", linestyle="--", linewidth=1.0)
    _axes[1].set_title("Edge-proportional ROI")
    _axes[1].set_xlabel("edge threshold")
    _axes[1].set_ylabel("ROI")
    _axes[1].grid(True, linewidth=0.4, alpha=0.4)
    _axes[1].legend()

    mo.vstack(
        [
            mo.md("threshold に対する ROI の形を見る。shift 後に曲線が上へ出るかを確認する。"),
            _fig,
        ]
    )
    return


@app.cell
def _(kelly_curve_df, mo, plt):
    # セル概要: Kelly bankroll curve を描画する。
    _fig, _ax = plt.subplots(figsize=(7.2, 4.8))
    for _variant_name, _part in kelly_curve_df.groupby("variant", dropna=False):
        _ax.plot(
            _part["race_i"].to_numpy(dtype=int),
            _part["bankroll_after"].to_numpy(dtype=float),
            label=str(_variant_name),
        )
    _ax.set_xlabel("race index")
    _ax.set_ylabel("bankroll")
    _ax.set_title("Kelly bankroll curve")
    _ax.grid(True, linewidth=0.4, alpha=0.4)
    _ax.legend()
    mo.vstack(
        [
            mo.md("資金曲線は上振れだけでなく、途中のドローダウンの大きさも一緒に見る。"),
            _fig,
        ]
    )
    return


@app.cell
def _(OUTPUT_DIR, mo):
    # セル概要: 保存先を表示する。
    mo.md(
        "\n".join(
            [
                "## 9. 出力ファイル",
                f"- output dir: `{OUTPUT_DIR}`",
                "- `variant_metrics.csv`",
                "- `variant_reliability.csv`",
                "- `variant_odds_band_reliability.csv`",
                "- `variant_odds_band_summary.csv`",
                "- `variant_odds_band_curve.csv`",
                "- `logit_shift_lambda_by_race.csv`",
                "- `strategy_summary_flat.csv`",
                "- `strategy_summary_edge.csv`",
                "- `strategy_summary_kelly.csv`",
                "- `strategy_kelly_curve.csv`",
            ]
        )
    )
    return


if __name__ == "__main__":
    app.run()
