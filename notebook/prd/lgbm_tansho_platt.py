import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import os
    import random
    import shlex
    import sys
    from datetime import datetime
    from pathlib import Path

    import lightgbm as lgb
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import yaml
    from pydantic import BaseModel, Field
    from sklearn.calibration import calibration_curve
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    return (
        BaseModel,
        Field,
        Path,
        brier_score_loss,
        calibration_curve,
        datetime,
        json,
        lgb,
        log_loss,
        mo,
        np,
        os,
        pd,
        plt,
        random,
        roc_auc_score,
        shlex,
        sys,
        yaml,
    )


@app.cell
def _(mo):
    _title_md = (
        "# LightGBM単勝版（Platt calibration + marimo最適化）\n\n"
        "- parquet を読み込み\n"
        "- Platt校正で `p_win` を補正\n"
        "- edge閾値シミュレーションまでを実行（重い解析は未実装）"
    )
    _title_view = mo.md(_title_md)
    _title_view
    return


@app.cell
def _():
    ODDS_COL = "odds"
    PLATT_ODDS_COL_DEFAULT = "j_odds_tansho"
    return ODDS_COL, PLATT_ODDS_COL_DEFAULT


@app.cell
def _(Path, sys):
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "prd"
    OUTPUT_DIR = NOTEBOOK_ROOT / "outputs"

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from harp.controllers import (
        NotebookFeatureConfigController,
        build_notebook_config,
    )
    from pipeline.runtime_settings import load_pipeline_runtime_config
    from harp.adapters.driven.storage import (
        dataframe_cache_exists,
        load_dataframe_cache,
        resolve_dataframe_cache_path,
    )
    from harp.shared.paths import notebook_analysis_cache_dir

    CACHE_DIR = notebook_analysis_cache_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    notebook_feature_config = NotebookFeatureConfigController(load_pipeline_runtime_config())
    return (
        CACHE_DIR,
        OUTPUT_DIR,
        PROJECT_ROOT,
        build_notebook_config,
        notebook_feature_config,
        dataframe_cache_exists,
        load_dataframe_cache,
        resolve_dataframe_cache_path,
    )


@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, notebook_feature_config):
    class RunConfig(BaseModel):
        test_year: int = Field(default=2025)
        train_year_start: int = Field(default=2013)
        train_year_end: int = Field(default=2024)
        tansho_type: str = Field(default="j_odds_tansho")
        global_seed: int = Field(default=42)
        main_parquet_path: str = Field(default="")
        odds_parquet_path: str = Field(default="")
        feature_set_name: str = Field(default="win_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        run_advanced_default: bool = Field(default=False)

    cfg = RunConfig()
    return (cfg,)


@app.cell
def _(cfg, mo):
    feature_set_name_widget = mo.ui.text(
        label="Feature set name",
        value=cfg.feature_set_name,
        placeholder="win_v1",
        full_width=True,
    )
    registry_path_widget = mo.ui.text(
        label="Registry path",
        value=cfg.registry_path,
        placeholder="pipeline/config/feature_registry.yml",
        full_width=True,
    )
    tansho_type_widget = mo.ui.dropdown(
        label="単勝オッズ列（校正/EV/edge）",
        options=["j_odds_tansho", "odds_tansho"],
        value=str(cfg.tansho_type),
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
    run_advanced_switch = mo.ui.switch(
        value=cfg.run_advanced_default,
        label="Run edge threshold simulation",
    )

    _settings_view = mo.vstack(
        [
            mo.md("## 実行設定"),
            feature_set_name_widget,
            registry_path_widget,
            main_parquet_path_widget,
            odds_parquet_path_widget,
            tansho_type_widget,
            mo.hstack([run_advanced_switch]),
            mo.md("- `Run edge threshold simulation` OFF: edge閾値シミュレーションをスキップ"),
        ]
    )
    _settings_view
    return (
        feature_set_name_widget,
        main_parquet_path_widget,
        odds_parquet_path_widget,
        registry_path_widget,
        run_advanced_switch,
        tansho_type_widget,
    )


@app.cell
def _(
    build_notebook_config,
    cfg,
    feature_set_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    odds_parquet_path_widget,
    CACHE_DIR,
    mo,
    registry_path_widget,
    run_advanced_switch,
    tansho_type_widget,
):
    if is_script_mode:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            cli_args=mo.cli_args(),
        )
    else:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            overrides={
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "odds_parquet_path": str(odds_parquet_path_widget.value).strip(),
                "registry_path": str(registry_path_widget.value).strip(),
                "run_advanced_default": bool(run_advanced_switch.value),
                "tansho_type": str(tansho_type_widget.value).strip(),
            },
        )

    resolved_cfg = resolved_cfg.model_copy(
        update={
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip()
            or str(
                CACHE_DIR
                / f"m_train_race_horse_past5_{resolved_cfg.train_year_start}_{resolved_cfg.test_year}.parquet"
            ),
            "odds_parquet_path": str(resolved_cfg.odds_parquet_path).strip()
            or str(CACHE_DIR / "race_odds.parquet"),
            "registry_path": str(resolved_cfg.registry_path).strip(),
            "run_advanced_default": bool(resolved_cfg.run_advanced_default),
            "tansho_type": str(resolved_cfg.tansho_type).strip(),
        }
    )

    if not resolved_cfg.feature_set_name:
        raise ValueError("feature_set_name is required.")
    if resolved_cfg.tansho_type not in {"j_odds_tansho", "odds_tansho"}:
        raise ValueError(f"Unsupported tansho odds type: {resolved_cfg.tansho_type}")
    resolved_run_advanced = bool(resolved_cfg.run_advanced_default)
    resolved_tansho_type = str(resolved_cfg.tansho_type)
    return resolved_cfg, resolved_run_advanced, resolved_tansho_type


@app.cell
def _(np, os, random, resolved_cfg):
    GLOBAL_SEED = int(resolved_cfg.global_seed)
    os.environ["PYTHONHASHSEED"] = str(GLOBAL_SEED)
    random.seed(GLOBAL_SEED)
    np.random.seed(GLOBAL_SEED)
    return (GLOBAL_SEED,)


@app.cell
def _(Path, resolved_cfg):
    MAIN_CACHE_PATH = Path(resolved_cfg.main_parquet_path)
    ODDS_CACHE_PATH = Path(resolved_cfg.odds_parquet_path)
    return MAIN_CACHE_PATH, ODDS_CACHE_PATH


@app.cell
def _(mo):
    _section_md = "## データ読み込み（parquet）"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(
    MAIN_CACHE_PATH,
    resolved_cfg,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    shlex,
):
    main_cache_exists = dataframe_cache_exists(MAIN_CACHE_PATH)
    if main_cache_exists:
        main_cache_source_path = resolve_dataframe_cache_path(MAIN_CACHE_PATH)
        print(f"[cache] load main: {main_cache_source_path}")
        df_main = load_dataframe_cache(MAIN_CACHE_PATH)
    else:
        _export_cmd = " ".join(
            [
                "scripts/refresh_analysis_cache.sh",
                "--skip-dbt",
                "--skip-odds",
                "--train-year-start",
                str(resolved_cfg.train_year_start),
                "--test-year",
                str(resolved_cfg.test_year),
                "--main-output",
                shlex.quote(str(MAIN_CACHE_PATH)),
            ]
        )
        raise ValueError(
            "Main parquet not found. Export it first.\n"
            f"missing_path={MAIN_CACHE_PATH}\n"
            f"run_command={_export_cmd}"
        )

    df_main.head(1)
    return (df_main,)


@app.cell
def _(
    ODDS_CACHE_PATH,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    shlex,
):
    odds_cache_exists = dataframe_cache_exists(ODDS_CACHE_PATH)
    if odds_cache_exists:
        odds_cache_source_path = resolve_dataframe_cache_path(ODDS_CACHE_PATH)
        print(f"[cache] load odds: {odds_cache_source_path}")
        df_odds = load_dataframe_cache(ODDS_CACHE_PATH)
    else:
        _export_cmd = " ".join(
            [
                "scripts/refresh_analysis_cache.sh",
                "--skip-dbt",
                "--train-year-start",
                str(resolved_cfg.train_year_start),
                "--test-year",
                str(resolved_cfg.test_year),
                "--odds-output",
                shlex.quote(str(ODDS_CACHE_PATH)),
            ]
        )
        raise ValueError(
            "Odds parquet not found. Export it first.\n"
            f"missing_path={ODDS_CACHE_PATH}\n"
            f"run_command={_export_cmd}"
        )

    df_odds.head(1)
    return (df_odds,)


@app.cell
def _(notebook_feature_config, resolved_cfg):
    from harp.core.training import build_binary_dataset

    _resolved_registry_path, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
    )
    return build_binary_dataset, cat_features, feature_names


@app.cell
def _(mo):
    _section_md = "## 学習データ作成"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(build_binary_dataset, cat_features, df_main, feature_names, np, pd, resolved_cfg):
    df_feat = df_main.copy()
    _held_dt = pd.to_datetime(df_feat["held_date"], errors="coerce")
    if _held_dt.isna().any():
        _bad_n = int(_held_dt.isna().sum())
        raise ValueError(f"held_date conversion failed: {_bad_n} rows")

    df_feat["held_year"] = _held_dt.dt.year.astype("int64")

    ds = build_binary_dataset(
        df=df_feat,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_win",
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        test_year=int(resolved_cfg.test_year),
    )

    _test_idx = ds.X_test.index.to_numpy()
    df_test_keys = pd.DataFrame(
        {
            "race_id": df_feat.loc[_test_idx, "race_id"].astype(str).values,
            "horse_number": df_feat.loc[_test_idx, "horse_number"].astype(int).values,
        }
    )

    (
        ds.X_tr.shape,
        ds.X_val.shape,
        ds.X_test.shape,
        len(np.unique(df_test_keys["race_id"].values)),
    )
    return df_feat, df_test_keys, ds


@app.cell
def _(mo):
    _section_md = "## モデル学習"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(GLOBAL_SEED, ds, lgb):
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
        "random_state": GLOBAL_SEED,
        "bagging_seed": GLOBAL_SEED,
        "feature_fraction_seed": GLOBAL_SEED,
        "data_random_seed": GLOBAL_SEED,
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": -1,
    }

    _fit_kwargs = {
        "eval_set": [(ds.X_val, ds.y_val)],
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(200, verbose=True),
            lgb.log_evaluation(period=50),
        ],
    }

    _train_result = train_binary_lgbm(ds=ds, model_params=model_params, fit_kwargs=_fit_kwargs)
    model = _train_result.model
    return model, model_params


@app.cell
def _(mo):
    _section_md = "## 評価データ作成（予測 + オッズ）"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(ODDS_COL, df_odds, df_test_keys, ds, model, pd, resolved_tansho_type):
    _pred_test = model.predict_proba(ds.X_test)[:, 1]

    _df_test = df_test_keys.copy()
    _df_test["y_true"] = ds.y_test.astype(int).values
    _df_test["p_win"] = _pred_test.astype(float)

    _odds_cols = [
        "race_id",
        "horse_number",
        "pay_tansho",
        "j_odds_tansho",
        "odds_tansho",
    ]

    _df_odds_use = df_odds.copy()
    _df_odds_use["race_id"] = _df_odds_use["race_id"].astype(str)
    _df_odds_use["horse_number"] = _df_odds_use["horse_number"].astype(int)

    _missing_odds_cols = [
        _col for _col in _odds_cols if _col not in _df_odds_use.columns
    ]
    if _missing_odds_cols:
        raise KeyError(f"race_odds missing columns: {_missing_odds_cols}")

    df_eval_raw = _df_test.merge(
        _df_odds_use[_odds_cols], on=["race_id", "horse_number"], how="left"
    )
    df_eval_raw[ODDS_COL] = pd.to_numeric(
        df_eval_raw[resolved_tansho_type], errors="coerce"
    ).astype(float)

    df_eval_raw = df_eval_raw.dropna(subset=[ODDS_COL]).copy()
    df_eval_raw["real_return_actual"] = (
        pd.to_numeric(df_eval_raw["pay_tansho"], errors="coerce").fillna(0.0) / 100.0
    )
    df_eval_raw["real_return"] = df_eval_raw["real_return_actual"]
    df_eval_raw["real_profit"] = df_eval_raw["real_return"] - 1.0
    df_eval_raw["ev_return"] = df_eval_raw["p_win"] * df_eval_raw[ODDS_COL]
    df_eval_raw["ev_profit"] = df_eval_raw["ev_return"] - 1.0
    return (df_eval_raw,)


@app.cell
def _(mo):
    _section_md = "## Platt校正（logit(p) + log(odds)）"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(
    ODDS_COL,
    OUTPUT_DIR,
    PLATT_ODDS_COL_DEFAULT,
    df_eval_raw,
    df_feat,
    ds,
    model,
    pd,
    resolved_cfg,
    resolved_tansho_type,
):
    from harp.core.training import apply_platt_logodds, fit_platt_logodds_oof

    platt_odds_col = PLATT_ODDS_COL_DEFAULT
    if platt_odds_col not in df_feat.columns:
        platt_odds_col = resolved_tansho_type
    if platt_odds_col not in df_feat.columns:
        raise KeyError(f"missing platt odds column in df_feat: {platt_odds_col}")
    if platt_odds_col not in df_eval_raw.columns:
        raise KeyError(f"missing platt odds column in df_eval_raw: {platt_odds_col}")

    platt_info = fit_platt_logodds_oof(
        model=model,
        ds=ds,
        df_meta=df_feat,
        odds_col=platt_odds_col,
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        valid_years_back=5,
        eps=1e-12,
    )

    fold_log_df = pd.DataFrame(platt_info.get("fold_metrics", []))
    _oof_path = OUTPUT_DIR / "win_oof_fold_metrics.csv"
    fold_log_df.to_csv(_oof_path, index=False)
    print(f"saved OOF fold metrics: {_oof_path.resolve()}")

    _payload = {
        "calibration": {
            "method": "platt_logodds",
            "params": platt_info,
        }
    }
    _p_base = (
        pd.to_numeric(df_eval_raw["p_win"], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .clip(0.0, 1.0)
    )

    df_eval = df_eval_raw.copy()
    df_eval["p_win_raw"] = _p_base
    df_eval["p_win_platt"] = apply_platt_logodds(
        base_proba=_p_base.to_numpy(),
        payload=_payload,
        df_feat=df_eval,
        odds_col=platt_odds_col,
    )
    df_eval["p_win"] = df_eval["p_win_platt"].astype(float)
    df_eval["ev_return"] = df_eval["p_win"] * df_eval[ODDS_COL]
    df_eval["ev_profit"] = df_eval["ev_return"] - 1.0

    _platt = platt_info.get("platt", {})
    print("Platt coef:", _platt.get("coef"))
    print("Platt intercept:", _platt.get("intercept"))
    return (df_eval,)


@app.cell
def _(mo):
    _section_md = "## メトリクス評価とログ保存"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(
    OUTPUT_DIR,
    brier_score_loss,
    datetime,
    df_eval,
    json,
    log_loss,
    model_params,
    pd,
    resolved_cfg,
    resolved_tansho_type,
    roc_auc_score,
):
    _y_true = df_eval["y_true"].astype(int).to_numpy()
    _pred = df_eval["p_win"].astype(float).to_numpy()
    _pred_clip = _pred.clip(1e-15, 1 - 1e-15)

    _auc = float(roc_auc_score(_y_true, _pred_clip))
    _brier = float(brier_score_loss(_y_true, _pred_clip))
    _ll = float(log_loss(_y_true, _pred_clip))

    eval_scores = {
        "auc": _auc,
        "brier": _brier,
        "logloss": _ll,
    }

    metrics_row = {
        "timestamp": datetime.now().isoformat(),
        "auc": _auc,
        "brier": _brier,
        "logloss": _ll,
        "n_test": int(len(_y_true)),
        "train_year_start": int(resolved_cfg.train_year_start),
        "train_year_end": int(resolved_cfg.train_year_end),
        "test_year": int(resolved_cfg.test_year),
        "tansho_type": resolved_tansho_type,
        "model_params": json.dumps(model_params, ensure_ascii=False),
    }

    _out_path = OUTPUT_DIR / "win_model_eval_log.csv"
    _new_df = pd.DataFrame([metrics_row])
    if _out_path.exists():
        _existing_df = pd.read_csv(_out_path)
        _out_df = pd.concat([_new_df, _existing_df], ignore_index=True)
    else:
        _out_df = _new_df
    _out_df.to_csv(_out_path, index=False)
    print(f"saved eval log: {_out_path.resolve()}")
    return (eval_scores,)


@app.cell
def _(eval_scores, mo):
    _metrics_view = mo.md(
        f"""
        - AUC: `{eval_scores['auc']:.6f}`
        - Brier: `{eval_scores['brier']:.6f}`
        - LogLoss: `{eval_scores['logloss']:.6f}`
        """
    )
    _metrics_view
    return


@app.cell
def _(OUTPUT_DIR, ds, model, pd):
    imp = (
        pd.DataFrame(
            {
                "feature": ds.X_tr.columns,
                "importance_gain": model.booster_.feature_importance(importance_type="gain"),
                "importance_split": model.booster_.feature_importance(importance_type="split"),
            }
        )
        .sort_values("importance_gain", ascending=False)
        .reset_index(drop=True)
    )

    _imp_path = OUTPUT_DIR / "win_feature_importance.csv"
    imp.to_csv(_imp_path, index=False)
    print(f"saved feature importance: {_imp_path.resolve()}")
    return (imp,)


@app.cell
def _(imp, mo):
    _imp_table = mo.ui.table(imp.head(30))
    _imp_view = mo.vstack(
        [
            mo.md("重要度上位30"),
            _imp_table,
        ]
    )
    _imp_view
    return


@app.cell
def _(mo):
    _section_md = "## 基本診断"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(df_eval, mo):
    _desc = (
        df_eval["p_win"]
        .describe()
        .rename_axis("metric")
        .reset_index(name="value")
    )
    _desc_table = mo.ui.table(_desc)
    _desc_view = mo.vstack([mo.md("`p_win` summary"), _desc_table])
    _desc_view
    return


@app.cell
def _(calibration_curve, df_eval, pd):
    _df_cal = df_eval[["p_win", "y_true"]].dropna().copy()
    _df_cal["p_win"] = _df_cal["p_win"].astype(float).clip(0.0, 1.0)
    _df_cal["y_true"] = _df_cal["y_true"].astype(int)

    n_bins = 10
    _df_cal["decile"] = pd.qcut(
        _df_cal["p_win"], q=n_bins, labels=False, duplicates="drop"
    )
    decile_table = (
        _df_cal.groupby("decile")
        .agg(
            n=("y_true", "size"),
            p_mean=("p_win", "mean"),
            y_rate=("y_true", "mean"),
            p_min=("p_win", "min"),
            p_max=("p_win", "max"),
        )
        .reset_index()
        .sort_values("decile")
    )

    _prob_true, _prob_pred = calibration_curve(
        _df_cal["y_true"].values,
        _df_cal["p_win"].values,
        n_bins=n_bins,
        strategy="quantile",
    )

    df_cal = _df_cal
    calib_curve_points = pd.DataFrame({"prob_pred": _prob_pred, "prob_true": _prob_true})
    return calib_curve_points, decile_table


@app.cell
def _(calib_curve_points, decile_table, mo):
    _calib_points_table = mo.ui.table(calib_curve_points)
    _decile_table = mo.ui.table(decile_table)
    _calib_table_view = mo.vstack(
        [
            mo.md("Calibration points"),
            _calib_points_table,
            mo.md("Decile summary"),
            _decile_table,
        ]
    )
    _calib_table_view
    return


@app.cell
def _(calib_curve_points, mo, plt):
    _fig, _ax = plt.subplots(figsize=(6, 6))
    _ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect")
    _ax.plot(
        calib_curve_points["prob_pred"].values,
        calib_curve_points["prob_true"].values,
        marker="o",
        label="model",
    )
    _ax.set_title("Calibration curve (quantile bins)")
    _ax.set_xlabel("mean predicted p_win")
    _ax.set_ylabel("observed win rate")
    _ax.grid(True, linewidth=0.4, alpha=0.4)
    _ax.legend()
    _calib_plot_view = mo.vstack([mo.md("Calibration curve"), _fig])
    _calib_plot_view
    return


@app.cell
def _(mo):
    _section_md = "## Edge閾値シミュレーション"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(mo, resolved_run_advanced):
    if resolved_run_advanced:
        edge_notice = mo.md("Edge simulation: ON")
    else:
        edge_notice = mo.md(
            "Edge simulation: OFF（閾値シミュレーションはスキップ。スイッチをONにすると実行）"
        )
    edge_notice
    return


@app.cell
def _():
    from harp.core.inference import prepare_edge_frame, simulate_edge_thresholds

    return prepare_edge_frame, simulate_edge_thresholds


@app.cell
def _(
    ODDS_COL,
    df_eval,
    np,
    pd,
    prepare_edge_frame,
    resolved_run_advanced,
    simulate_edge_thresholds,
):
    if not resolved_run_advanced:
        strategy_details_edge = pd.DataFrame()
        strategy_details_flat = pd.DataFrame()
        strategy_summary_edge = pd.DataFrame()
        strategy_summary_flat = pd.DataFrame()
    else:
        _edge_frame = prepare_edge_frame(
            df_eval,
            prob_col="p_win",
            odds_col=ODDS_COL,
            label_col="y_true",
            ev_profit_col="ev_profit",
            realized_payout_col="real_return",
        )
        _thresholds = np.round(np.arange(0.0, 0.31, 0.01), 2).tolist()

        strategy_summary_flat, strategy_details_flat = simulate_edge_thresholds(
            _edge_frame,
            thresholds=_thresholds,
            selection_mode="top_n_per_race",
            top_n=1,
            stake_mode="flat",
            stake=1.0,
        )
        strategy_summary_edge, strategy_details_edge = simulate_edge_thresholds(
            _edge_frame,
            thresholds=_thresholds,
            selection_mode="top_n_per_race",
            top_n=1,
            stake_mode="edge_proportional",
            edge_unit=0.1,
            stake_at_edge_unit=1.0,
        )
    return (
        strategy_details_edge,
        strategy_details_flat,
        strategy_summary_edge,
        strategy_summary_flat,
    )


@app.cell
def _(
    mo,
    resolved_run_advanced,
    strategy_details_edge,
    strategy_details_flat,
    strategy_summary_edge,
    strategy_summary_flat,
):
    if not resolved_run_advanced:
        strategy_output = mo.md("Edge threshold simulation: skipped")
    else:
        _summary_flat = mo.ui.table(strategy_summary_flat)
        _summary_edge = mo.ui.table(strategy_summary_edge)
        _details_flat = mo.ui.table(strategy_details_flat.head(50))
        _details_edge = mo.ui.table(strategy_details_edge.head(50))
        strategy_output = mo.vstack(
            [
                mo.md("Edge threshold simulation: completed"),
                mo.md("### Flat stake summary"),
                _summary_flat,
                mo.md("### Edge-proportional stake summary"),
                _summary_edge,
                mo.md("### Flat stake details (head)"),
                _details_flat,
                mo.md("### Edge-proportional details (head)"),
                _details_edge,
            ]
        )
    strategy_output
    return


if __name__ == "__main__":
    app.run()
