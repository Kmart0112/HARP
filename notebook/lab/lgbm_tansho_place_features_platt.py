import marimo

__generated_with = "0.22.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # Import notebook runtime, modeling, and plotting dependencies.
    import json
    import os
    import random
    import shlex
    import sys
    from datetime import datetime
    from pathlib import Path

    import lightgbm as lgb
    import matplotlib.pyplot as plt
    import marimo as mo
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel, Field
    from sklearn.calibration import calibration_curve

    return (
        BaseModel,
        Field,
        Path,
        calibration_curve,
        datetime,
        json,
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


@app.cell(hide_code=True)
def _(mo):
    # Describe the notebook goal and the current modeling assumptions.
    title_view = mo.md(
        """
        # LGBM Tansho Platt (place_v1 features)

        - 単勝 `is_win` を分類で学習
        - 複勝と同じく `place_v1` 特徴量を既定で利用
        - `logit(p_raw) + log(単勝オッズ)` で Platt calibration を実施
        - Platt 後に race 単位で合計 1 へ合わせる `logit shift` も適用
        - `platt_shift` を使い、市場確率 `0.8 / odds` との edge で購入シミュレーションも行う
        - notebook は `marimo` / script mode 両対応
        """
    )
    title_view
    return


@app.cell(hide_code=True)
def _(mo):
    # Introduce the configuration section for script and interactive runs.
    _section_view = mo.md(
        """
        ## 1. 実行設定

        script mode では CLI 引数、interactive mode では下の UI 値を使います。
        まずは `place_v1` をそのまま既定にして、単勝ラベルだけ `is_win` に切り替えます。
        """
    )
    _section_view
    return


@app.cell
def _(Path, sys):
    # Resolve project paths and import notebook-facing driver/driven adapters.
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "lab"
    OUTPUT_DIR = NOTEBOOK_ROOT / "outputs" / "lgbm_tansho_place_features_platt"
    ARTIFACT_DIR = OUTPUT_DIR / "artifacts"
    METADATA_DIR = OUTPUT_DIR / "metadata"
    MODEL_EVAL_LOG_PATH = OUTPUT_DIR / "model_eval_log.csv"
    OOF_LOG_PATH = OUTPUT_DIR / "platt_oof_fold_metrics.csv"
    FEATURE_IMPORTANCE_PATH = OUTPUT_DIR / "feature_importance.csv"
    LOGIT_SHIFT_LAMBDA_PATH = OUTPUT_DIR / "logit_shift_lambda_by_race.csv"
    STRATEGY_SUMMARY_TOP1_PATH = OUTPUT_DIR / "strategy_summary_top1.csv"
    STRATEGY_DETAILS_TOP1_PATH = OUTPUT_DIR / "strategy_details_top1.csv"

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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    notebook_feature_config = NotebookFeatureConfigController(load_pipeline_runtime_config())
    return (
        ARTIFACT_DIR,
        FEATURE_IMPORTANCE_PATH,
        LOGIT_SHIFT_LAMBDA_PATH,
        METADATA_DIR,
        MODEL_EVAL_LOG_PATH,
        OOF_LOG_PATH,
        STRATEGY_DETAILS_TOP1_PATH,
        STRATEGY_SUMMARY_TOP1_PATH,
        build_notebook_config,
        dataframe_cache_exists,
        notebook_feature_config,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        resolve_dataframe_cache_path,
    )


@app.cell
def _(mo):
    # Detect whether marimo is running as a script for CLI execution.
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(ARTIFACT_DIR, BaseModel, Field, METADATA_DIR, notebook_feature_config):
    # Define notebook configuration defaults for repeatable runs.
    default_artifact_path = str(ARTIFACT_DIR / "is_win_place_features_platt_notebook_v1.pkl")
    default_manifest_path = str(METADATA_DIR / "is_win_place_features_platt_notebook_v1.json")

    class RunConfig(BaseModel):
        test_year: int = Field(default=2025)
        train_year_start: int = Field(default=2013)
        train_year_end: int = Field(default=2024)
        global_seed: int = Field(default=42)
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        resolved_features_config_path: str = Field(default="")
        calibration_odds_col: str = Field(default="j_odds_tansho")
        main_parquet_path: str = Field(default="")
        odds_parquet_path: str = Field(default="")
        save_artifact: bool = Field(default=False)
        artifact_path: str = Field(default=default_artifact_path)
        manifest_path: str = Field(default=default_manifest_path)
        valid_years_back: int = Field(default=5)
        threshold_min: float = Field(default=0.0)
        threshold_max: float = Field(default=0.30)
        threshold_step: float = Field(default=0.01)

    cfg = RunConfig()
    return (cfg,)


@app.cell
def _(cfg, mo):
    # Build interactive controls for the main notebook settings.
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
    resolved_features_config_path_widget = mo.ui.text(
        label="Resolved feature config path",
        value=cfg.resolved_features_config_path,
        placeholder="optional rendered YAML",
        full_width=True,
    )
    calibration_odds_col_widget = mo.ui.dropdown(
        label="Calibration odds column",
        options=["j_odds_tansho", "odds_tansho"],
        value=cfg.calibration_odds_col,
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
    save_artifact_switch = mo.ui.switch(
        value=cfg.save_artifact,
        label="Save artifact",
    )
    artifact_path_widget = mo.ui.text(
        label="Artifact path",
        value=cfg.artifact_path,
        full_width=True,
    )
    manifest_path_widget = mo.ui.text(
        label="Manifest path",
        value=cfg.manifest_path,
        full_width=True,
    )
    threshold_min_widget = mo.ui.number(
        label="Edge threshold min",
        start=0.0,
        stop=1.0,
        step=0.01,
        value=cfg.threshold_min,
    )
    threshold_max_widget = mo.ui.number(
        label="Edge threshold max",
        start=0.0,
        stop=1.0,
        step=0.01,
        value=cfg.threshold_max,
    )
    threshold_step_widget = mo.ui.number(
        label="Edge threshold step",
        start=0.001,
        stop=1.0,
        step=0.001,
        value=cfg.threshold_step,
    )

    settings_view = mo.vstack(
        [
            feature_set_name_widget,
            registry_path_widget,
            resolved_features_config_path_widget,
            calibration_odds_col_widget,
            mo.md("`main_parquet_path` を空欄にすると標準 analysis cache を参照します。"),
            main_parquet_path_widget,
            odds_parquet_path_widget,
            mo.hstack([threshold_min_widget, threshold_max_widget, threshold_step_widget]),
            mo.hstack([save_artifact_switch]),
            artifact_path_widget,
            manifest_path_widget,
        ]
    )
    settings_view
    return (
        artifact_path_widget,
        calibration_odds_col_widget,
        feature_set_name_widget,
        main_parquet_path_widget,
        manifest_path_widget,
        odds_parquet_path_widget,
        registry_path_widget,
        resolved_features_config_path_widget,
        save_artifact_switch,
        threshold_max_widget,
        threshold_min_widget,
        threshold_step_widget,
    )


@app.cell
def _(
    artifact_path_widget,
    build_notebook_config,
    calibration_odds_col_widget,
    cfg,
    feature_set_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    manifest_path_widget,
    mo,
    notebook_analysis_cache_dir,
    odds_parquet_path_widget,
    registry_path_widget,
    resolved_features_config_path_widget,
    save_artifact_switch,
    threshold_max_widget,
    threshold_min_widget,
    threshold_step_widget,
):
    # Resolve a single config object from CLI args or interactive widget values.
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
                "artifact_path": str(artifact_path_widget.value).strip(),
                "calibration_odds_col": str(calibration_odds_col_widget.value).strip(),
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "manifest_path": str(manifest_path_widget.value).strip(),
                "odds_parquet_path": str(odds_parquet_path_widget.value).strip(),
                "registry_path": str(registry_path_widget.value).strip(),
                "resolved_features_config_path": str(
                    resolved_features_config_path_widget.value
                ).strip(),
                "save_artifact": bool(save_artifact_switch.value),
                "threshold_max": float(threshold_max_widget.value),
                "threshold_min": float(threshold_min_widget.value),
                "threshold_step": float(threshold_step_widget.value),
            },
        )

    default_cache_dir = notebook_analysis_cache_dir()
    resolved_cfg = resolved_cfg.model_copy(
        update={
            "artifact_path": str(resolved_cfg.artifact_path).strip(),
            "calibration_odds_col": str(resolved_cfg.calibration_odds_col).strip(),
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip()
            or str(
                default_cache_dir
                / f"m_train_race_horse_past5_{resolved_cfg.train_year_start}_{resolved_cfg.test_year}.parquet"
            ),
            "manifest_path": str(resolved_cfg.manifest_path).strip(),
            "odds_parquet_path": str(resolved_cfg.odds_parquet_path).strip()
            or str(default_cache_dir / "race_odds.parquet"),
            "registry_path": str(resolved_cfg.registry_path).strip(),
            "resolved_features_config_path": str(
                resolved_cfg.resolved_features_config_path
            ).strip(),
            "save_artifact": bool(resolved_cfg.save_artifact),
            "threshold_max": float(resolved_cfg.threshold_max),
            "threshold_min": float(resolved_cfg.threshold_min),
            "threshold_step": float(resolved_cfg.threshold_step),
            "valid_years_back": int(resolved_cfg.valid_years_back),
        }
    )

    resolved_save_artifact = bool(resolved_cfg.save_artifact)

    if not resolved_cfg.feature_set_name and not resolved_cfg.resolved_features_config_path:
        raise ValueError("feature_set_name is required.")
    if not resolved_cfg.main_parquet_path:
        raise ValueError("main_parquet_path is required.")
    if not resolved_cfg.odds_parquet_path:
        raise ValueError("odds_parquet_path is required.")
    if resolved_cfg.calibration_odds_col not in {"j_odds_tansho", "odds_tansho"}:
        raise ValueError(
            f"Unsupported calibration_odds_col: {resolved_cfg.calibration_odds_col}"
        )
    if resolved_cfg.valid_years_back < 1:
        raise ValueError("valid_years_back must be >= 1.")
    if resolved_cfg.threshold_step <= 0.0:
        raise ValueError("threshold_step must be positive.")
    if resolved_cfg.threshold_max < resolved_cfg.threshold_min:
        raise ValueError("threshold_max must be >= threshold_min.")
    if resolved_save_artifact and (not resolved_cfg.artifact_path or not resolved_cfg.manifest_path):
        raise ValueError("artifact_path and manifest_path are required when save_artifact is enabled.")
    return resolved_cfg, resolved_save_artifact


@app.cell
def _(np, os, random, resolved_cfg):
    # Fix all notebook-level random seeds for reproducibility.
    os.environ["PYTHONHASHSEED"] = str(resolved_cfg.global_seed)
    random.seed(resolved_cfg.global_seed)
    np.random.seed(resolved_cfg.global_seed)
    return


@app.cell(hide_code=True)
def _(mo):
    # Introduce the cache-backed dataset loading step.
    _section_view = mo.md(
        """
        ## 2. データ読み込み

        `mart.m_train_race_horse_past5` と `race_odds` の analysis cache を読みます。
        cache がなければ export コマンドを表示して止めます。
        """
    )
    _section_view
    return


@app.cell
def _(Path, resolved_cfg):
    # Normalize the configured cache paths as Path objects.
    cache_path = Path(resolved_cfg.main_parquet_path)
    odds_path = Path(resolved_cfg.odds_parquet_path)
    return cache_path, odds_path


@app.cell
def _(
    cache_path,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    resolved_cfg,
    shlex,
):
    # Load the main training cache or surface the exact refresh command.
    if dataframe_cache_exists(cache_path):
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] load main: {cache_source_path}")
        df_main = load_dataframe_cache(cache_path)
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
                shlex.quote(str(cache_path)),
            ]
        )
        raise ValueError(
            "Main parquet not found. Export it first.\n"
            f"missing_path={cache_path}\n"
            f"run_command={_export_cmd}"
        )

    df_main.head(1)
    return (df_main,)


@app.cell
def _(odds_path, pd, resolved_cfg, shlex):
    # Load the odds cache used for payout-based strategy simulation.
    if odds_path.exists():
        print(f"[cache] load odds: {odds_path}")
        df_odds = pd.read_parquet(odds_path)
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
                shlex.quote(str(odds_path)),
            ]
        )
        raise ValueError(
            "Odds parquet not found. Export it first.\n"
            f"missing_path={odds_path}\n"
            f"run_command={_export_cmd}"
        )

    df_odds.head(1)
    return (df_odds,)


@app.cell(hide_code=True)
def _(mo):
    # Introduce feature resolution and train/val/test split creation.
    _section_view = mo.md(
        """
        ## 3. 特徴量解決と split

        既定では `place_v1` を registry から解決し、target だけ `is_win` に切り替えます。
        これで「複勝と同じ説明変数で単勝を学習する」状態をそのまま試せます。
        """
    )
    _section_view
    return


@app.cell
def _(notebook_feature_config, resolved_cfg):
    # Resolve feature names and categorical columns from the registry or rendered config.
    from harp.core.training import build_binary_dataset

    feature_source, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
        resolved_features_config_path=resolved_cfg.resolved_features_config_path,
    )
    return build_binary_dataset, cat_features, feature_names, feature_source


@app.cell
def _(feature_names, feature_source, mo, resolved_cfg):
    # Summarize the resolved feature source for quick sanity checking.
    feature_summary_view = mo.vstack(
        [
            mo.md(f"- feature source: `{feature_source}`"),
            mo.md(f"- feature set name: `{resolved_cfg.feature_set_name}`"),
            mo.md(f"- feature count: `{len(feature_names)}`"),
        ]
    )
    feature_summary_view
    return


@app.cell
def _(
    build_binary_dataset,
    cat_features,
    df_main,
    feature_names,
    pd,
    resolved_cfg,
):
    # Build the year-based binary dataset for the win target.
    df_feat = df_main.copy()
    held_dt = pd.to_datetime(df_feat["held_date"], errors="coerce")
    if held_dt.isna().any():
        bad_n = int(held_dt.isna().sum())
        raise ValueError(f"held_date conversion failed: {bad_n} rows")

    df_feat["held_year"] = held_dt.dt.year.astype("int64")

    ds = build_binary_dataset(
        df=df_feat,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_win",
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        test_year=int(resolved_cfg.test_year),
    )
    return df_feat, ds


@app.cell
def _(df_feat, ds, pd, resolved_cfg):
    # Assemble test-set metadata needed for calibration and diagnostics.
    test_idx = ds.X_test.index.to_numpy()
    meta_cols = ["race_id", "horse_number", "horse_name", "held_date"]
    missing_meta_cols = [col for col in meta_cols if col not in df_feat.columns]
    if missing_meta_cols:
        raise KeyError(f"missing meta columns: {missing_meta_cols}")

    df_test_meta = df_feat.loc[test_idx, meta_cols].copy()
    df_test_meta["race_id"] = df_test_meta["race_id"].astype(str)
    df_test_meta["horse_number"] = pd.to_numeric(
        df_test_meta["horse_number"], errors="coerce"
    ).astype("Int64")
    return (df_test_meta,)


@app.cell
def _(ds, mo):
    # Show split sizes so the run window is visible without opening the code.
    split_info = ds.split_info
    split_summary_view = mo.vstack(
        [
            mo.md(f"- train rows: `{split_info['n_train_rows']}`"),
            mo.md(f"- val rows: `{split_info['n_val_rows']}`"),
            mo.md(f"- test rows: `{split_info['n_test_rows']}`"),
            mo.md(
                f"- window: `{split_info['train_year_start']} -> {split_info['train_year_end']} -> {split_info['test_year']}`"
            ),
        ]
    )
    split_summary_view
    return


@app.cell(hide_code=True)
def _(mo):
    # Introduce the model fitting step.
    _section_view = mo.md(
        """
        ## 4. 学習

        LightGBM のハイパーパラメータは既存単勝 notebook と揃えています。
        まず raw 確率を作り、その後で Platt を重ねます。
        """
    )
    _section_view
    return


@app.cell
def _(lgb, np, resolved_cfg):
    # Define the deterministic LightGBM parameter set used for this notebook.
    global_seed = int(resolved_cfg.global_seed)
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
        "random_state": global_seed,
        "bagging_seed": global_seed,
        "feature_fraction_seed": global_seed,
        "data_random_seed": global_seed,
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": -1,
    }
    fit_kwargs = {
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(200, verbose=True),
            lgb.log_evaluation(period=50),
        ],
    }
    np.array([global_seed]).item()
    return fit_kwargs, model_params


@app.cell
def _(ds, fit_kwargs, model_params):
    # Train the LightGBM binary classifier on the resolved feature set.
    from harp.core.training import train_binary_lgbm

    result = train_binary_lgbm(
        ds=ds,
        model_params=model_params,
        fit_kwargs={
            **fit_kwargs,
            "eval_set": [(ds.X_val, ds.y_val)],
        },
    )
    return (result,)


@app.cell
def _(ds, result):
    # Generate raw probabilities for the held-out test split.
    raw_test_proba = result.model.predict_proba(ds.X_test)[:, 1].astype(float)
    return (raw_test_proba,)


@app.cell(hide_code=True)
def _(mo):
    # Introduce calibration and held-out evaluation.
    _section_view = mo.md(
        """
        ## 5. Platt 校正と評価

        校正は train split 内の時系列 OOF で学習し、test split へ適用します。
        その後に race 単位の `logit shift` をかけて確率合計を 1 にそろえます。
        AUC は順位付けを見るので大きくは変わらず、Brier / LogLoss と race sum の整合性を見ます。
        """
    )
    _section_view
    return


@app.cell
def _(
    LOGIT_SHIFT_LAMBDA_PATH,
    OOF_LOG_PATH,
    df_feat,
    df_odds,
    df_test_meta,
    ds,
    np,
    pd,
    raw_test_proba,
    resolved_cfg,
    result,
):
    # Fit Platt calibration, then apply race-level logit shift to sum probabilities to 1.
    from harp.core.training import (
        apply_logit_shift_grouped,
        apply_platt_logodds,
        fit_platt_logodds_oof,
    )

    platt_info = fit_platt_logodds_oof(
        model=result.model,
        ds=ds,
        df_meta=df_feat,
        odds_col=resolved_cfg.calibration_odds_col,
        train_year_start=int(resolved_cfg.train_year_start),
        train_year_end=int(resolved_cfg.train_year_end),
        valid_years_back=int(resolved_cfg.valid_years_back),
        eps=1e-12,
    )

    fold_log_df = pd.DataFrame(platt_info.get("fold_metrics", []))
    fold_log_df.to_csv(OOF_LOG_PATH, index=False)
    print(f"saved OOF fold metrics: {OOF_LOG_PATH.resolve()}")

    _payload = {
        "calibration": {
            "method": "platt_logodds",
            "params": platt_info,
        }
    }
    df_eval = df_test_meta.copy()
    df_eval.index = ds.X_test.index
    df_eval["y_true"] = ds.y_test.astype(int).values
    df_eval["p_win_raw"] = raw_test_proba
    df_eval[resolved_cfg.calibration_odds_col] = pd.to_numeric(
        df_feat.loc[ds.X_test.index, resolved_cfg.calibration_odds_col],
        errors="coerce",
    ).astype(float)
    df_eval["p_win_platt"] = apply_platt_logodds(
        base_proba=df_eval["p_win_raw"].to_numpy(),
        payload=_payload,
        df_feat=df_eval,
        odds_col=resolved_cfg.calibration_odds_col,
    )
    k_by_group = (
        df_eval.groupby("race_id", dropna=False)["race_id"].size().astype(float).map(lambda _: 1.0).to_dict()
    )
    p_win_logit_shift, lambda_by_race = apply_logit_shift_grouped(
        df_eval["p_win_platt"].to_numpy(dtype=float),
        df_eval["race_id"].to_numpy(dtype=object),
        k_by_group=k_by_group,
        return_lambda=True,
    )
    df_eval["p_win_logit_shift"] = np.asarray(p_win_logit_shift, dtype=float)
    df_eval["p_win_platt_shift"] = df_eval["p_win_logit_shift"].astype(float)

    odds_cols = [
        "race_id",
        "horse_number",
        "pay_tansho",
        "j_odds_tansho",
        "odds_tansho",
    ]
    missing_odds_cols = [col for col in odds_cols if col not in df_odds.columns]
    if missing_odds_cols:
        raise KeyError(f"race_odds missing columns: {missing_odds_cols}")

    odds_use = df_odds[odds_cols].copy()
    odds_use["race_id"] = odds_use["race_id"].astype(str)
    odds_use["horse_number"] = pd.to_numeric(
        odds_use["horse_number"], errors="coerce"
    ).astype("Int64")

    df_eval = df_eval.merge(
        odds_use,
        on=["race_id", "horse_number"],
        how="left",
        suffixes=("", "_odds_cache"),
    )
    cache_odds_col = f"{resolved_cfg.calibration_odds_col}_odds_cache"
    if cache_odds_col in df_eval.columns:
        df_eval[resolved_cfg.calibration_odds_col] = pd.to_numeric(
            df_eval[cache_odds_col], errors="coerce"
        ).combine_first(
            pd.to_numeric(df_eval[resolved_cfg.calibration_odds_col], errors="coerce")
        )
    df_eval[resolved_cfg.calibration_odds_col] = pd.to_numeric(
        df_eval[resolved_cfg.calibration_odds_col], errors="coerce"
    ).astype(float)
    df_eval["real_return_actual"] = (
        pd.to_numeric(df_eval["pay_tansho"], errors="coerce").fillna(0.0).astype(float)
        / 100.0
    )
    df_eval["real_return"] = df_eval["real_return_actual"]
    df_eval["real_profit"] = df_eval["real_return"] - 1.0

    lambda_df = pd.DataFrame(
        {
            "race_id": list(lambda_by_race.keys()),
            "lambda_logit_shift": list(lambda_by_race.values()),
        }
    ).sort_values("race_id")
    lambda_df.to_csv(LOGIT_SHIFT_LAMBDA_PATH, index=False)
    print(f"saved logit shift lambdas: {LOGIT_SHIFT_LAMBDA_PATH.resolve()}")

    platt = platt_info.get("platt", {})
    print("Platt coef:", platt.get("coef"))
    print("Platt intercept:", platt.get("intercept"))
    return df_eval, lambda_df, platt_info


@app.cell
def _(df_eval, np, pd):
    # Calculate raw vs calibrated vs shifted metrics in a shared comparison table.
    from harp.core.training.metrics import calc_binary_metrics

    raw_metrics = calc_binary_metrics(df_eval["y_true"], df_eval["p_win_raw"].to_numpy())
    platt_metrics = calc_binary_metrics(df_eval["y_true"], df_eval["p_win_platt"].to_numpy())
    shifted_metrics = calc_binary_metrics(
        df_eval["y_true"], df_eval["p_win_logit_shift"].to_numpy()
    )

    race_sum_df = (
        df_eval.groupby("race_id", dropna=False)
        .agg(
            raw_sum=("p_win_raw", "sum"),
            platt_sum=("p_win_platt", "sum"),
            shifted_sum=("p_win_logit_shift", "sum"),
        )
        .reset_index()
    )

    metrics_df = pd.DataFrame(
        [
            {
                "variant": "raw",
                **raw_metrics,
                "mean_prob": float(df_eval["p_win_raw"].mean()),
                "race_sum_mae_vs_1": float(np.abs(race_sum_df["raw_sum"] - 1.0).mean()),
            },
            {
                "variant": "platt",
                **platt_metrics,
                "mean_prob": float(df_eval["p_win_platt"].mean()),
                "race_sum_mae_vs_1": float(np.abs(race_sum_df["platt_sum"] - 1.0).mean()),
            },
            {
                "variant": "logit_shift",
                **shifted_metrics,
                "mean_prob": float(df_eval["p_win_logit_shift"].mean()),
                "race_sum_mae_vs_1": float(np.abs(race_sum_df["shifted_sum"] - 1.0).mean()),
            },
        ]
    )
    return metrics_df, platt_metrics, race_sum_df


@app.cell
def _(metrics_df, mo):
    # Present the metric comparison table in the notebook UI.
    metrics_table = mo.ui.table(metrics_df)
    metrics_table
    return


@app.cell(hide_code=True)
def _(mo):
    # Explain how to interpret the metric table before looking at numbers.
    interpretation_view = mo.md(
        """
        指標の見方:

        - `AUC`: どれだけ勝ち馬を上位に置けるか。校正で大きくは動かないのが自然です。
        - `Brier`: 確率誤差の二乗平均。小さいほど良いです。
        - `LogLoss`: 高確信ミスへの罰が強い指標。Platt の主改善点はここを期待します。
        - `race_sum_mae_vs_1`: 各レースの確率合計が 1 からどれだけズレたかです。`logit_shift` ではほぼ 0 を期待します。
        """
    )
    interpretation_view
    return


@app.cell
def _(
    MODEL_EVAL_LOG_PATH,
    datetime,
    json,
    metrics_df,
    model_params,
    pd,
    resolved_cfg,
):
    # Append the current run summary to a notebook-local metrics log CSV.
    metrics_lookup = {
        row["variant"]: row for row in metrics_df.to_dict(orient="records")
    }
    row = {
        "timestamp": datetime.now().isoformat(),
        "feature_set_name": resolved_cfg.feature_set_name,
        "calibration_odds_col": resolved_cfg.calibration_odds_col,
        "train_year_start": int(resolved_cfg.train_year_start),
        "train_year_end": int(resolved_cfg.train_year_end),
        "test_year": int(resolved_cfg.test_year),
        "raw_auc": metrics_lookup["raw"]["auc"],
        "raw_brier": metrics_lookup["raw"]["brier"],
        "raw_logloss": metrics_lookup["raw"]["logloss"],
        "platt_auc": metrics_lookup["platt"]["auc"],
        "platt_brier": metrics_lookup["platt"]["brier"],
        "platt_logloss": metrics_lookup["platt"]["logloss"],
        "shifted_auc": metrics_lookup["logit_shift"]["auc"],
        "shifted_brier": metrics_lookup["logit_shift"]["brier"],
        "shifted_logloss": metrics_lookup["logit_shift"]["logloss"],
        "model_params": json.dumps(model_params, ensure_ascii=False),
    }

    log_df = pd.DataFrame([row])
    if MODEL_EVAL_LOG_PATH.exists():
        existing = pd.read_csv(MODEL_EVAL_LOG_PATH)
        out_df = pd.concat([log_df, existing], ignore_index=True)
    else:
        out_df = log_df
    out_df.to_csv(MODEL_EVAL_LOG_PATH, index=False)
    print(f"saved eval log: {MODEL_EVAL_LOG_PATH.resolve()}")
    return


@app.cell
def _(FEATURE_IMPORTANCE_PATH, ds, pd, result):
    # Export feature importance so the run can be compared outside the notebook.
    importance_df = (
        pd.DataFrame(
            {
                "feature": ds.X_tr.columns,
                "importance_gain": result.model.booster_.feature_importance(
                    importance_type="gain"
                ),
                "importance_split": result.model.booster_.feature_importance(
                    importance_type="split"
                ),
            }
        )
        .sort_values("importance_gain", ascending=False)
        .reset_index(drop=True)
    )
    importance_df.to_csv(FEATURE_IMPORTANCE_PATH, index=False)
    print(f"saved feature importance: {FEATURE_IMPORTANCE_PATH.resolve()}")
    return (importance_df,)


@app.cell
def _(importance_df, mo):
    # Show the top features for a quick post-run inspection.
    importance_view = mo.vstack(
        [
            mo.md("重要度上位30"),
            mo.ui.table(importance_df.head(30)),
        ]
    )
    importance_view
    return


@app.cell(hide_code=True)
def _(mo):
    # Introduce calibration diagnostics with interpretation guidance.
    _section_view = mo.md(
        """
        ## 6. 校正診断

        calibration curve は対角線に近いほど良いです。
        raw / platt / logit shift を並べて、特に高確率帯の過信と race 合計 1 の両立を見ます。
        """
    )
    _section_view
    return


@app.cell
def _(calibration_curve, df_eval, np, pd):
    # Compute calibration curves and decile summaries for raw, platt, and shifted outputs.
    curve_frames = []
    decile_frames = []
    for _variant, _prob_col in [
        ("raw", "p_win_raw"),
        ("platt", "p_win_platt"),
        ("logit_shift", "p_win_logit_shift"),
    ]:
        _work = df_eval[["y_true", _prob_col]].dropna().copy()
        _work["prob"] = pd.to_numeric(_work[_prob_col], errors="coerce").clip(0.0, 1.0)
        _work["y_true"] = _work["y_true"].astype(int)
        _work["decile"] = pd.qcut(
            _work["prob"],
            q=min(10, max(2, int(_work["prob"].nunique()))),
            labels=False,
            duplicates="drop",
        )

        _decile_table = (
            _work.groupby("decile")
            .agg(
                n=("y_true", "size"),
                p_mean=("prob", "mean"),
                y_rate=("y_true", "mean"),
                p_min=("prob", "min"),
                p_max=("prob", "max"),
            )
            .reset_index()
            .sort_values("decile")
        )
        _decile_table["variant"] = _variant
        decile_frames.append(_decile_table)

        _prob_true, _prob_pred = calibration_curve(
            _work["y_true"].to_numpy(dtype=int),
            _work["prob"].to_numpy(dtype=float),
            n_bins=min(10, max(2, int(_work["prob"].nunique()))),
            strategy="quantile",
        )
        curve_frames.append(
            pd.DataFrame(
                {
                    "variant": _variant,
                    "prob_pred": _prob_pred,
                    "prob_true": _prob_true,
                }
            )
        )

    curve_df = pd.concat(curve_frames, ignore_index=True)
    decile_df = pd.concat(decile_frames, ignore_index=True)
    np.array([len(curve_df)]).item()
    return curve_df, decile_df


@app.cell
def _(curve_df, decile_df, mo):
    # Render the curve points and decile diagnostics as tables.
    calibration_tables_view = mo.vstack(
        [
            mo.md("Calibration points"),
            mo.ui.table(curve_df),
            mo.md("Decile summary"),
            mo.ui.table(decile_df),
        ]
    )
    calibration_tables_view
    return


@app.cell
def _(curve_df, mo, plt):
    # Plot the raw, calibrated, and shifted calibration curves on the same axes.
    _fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect")

    for _variant in ["raw", "platt", "logit_shift"]:
        _part = curve_df.loc[curve_df["variant"] == _variant]
        ax.plot(
            _part["prob_pred"].to_numpy(),
            _part["prob_true"].to_numpy(),
            marker="o",
            label=_variant,
        )

    ax.set_title("Calibration curve (quantile bins)")
    ax.set_xlabel("mean predicted probability")
    ax.set_ylabel("observed win rate")
    ax.grid(True, linewidth=0.4, alpha=0.4)
    ax.legend()

    calibration_plot_view = mo.vstack([mo.md("Calibration curve"), _fig])
    calibration_plot_view
    return


@app.cell(hide_code=True)
def _(mo):
    # Introduce edge-threshold strategy simulation and how to read it.
    _section_view = mo.md(
        """
        ## 7. 購入シミュレーション

        `platt_shift` を採用し、市場確率を `0.8 / odds` として edge を計算します。
        各レースで edge 最大の 1 頭だけを候補にし、threshold をスライドして ROI を見ます。
        ROI は `total_return / total_stake` なので、`1.0` 超なら回収率 100% 超です。
        """
    )
    _section_view
    return


@app.cell
def _(
    STRATEGY_DETAILS_TOP1_PATH,
    STRATEGY_SUMMARY_TOP1_PATH,
    df_eval,
    np,
    prepare_edge_frame,
    resolved_cfg,
    simulate_edge_thresholds,
):
    # Run top-1-per-race flat betting simulation over a sliding edge threshold grid.
    thresholds = np.round(
        np.arange(
            float(resolved_cfg.threshold_min),
            float(resolved_cfg.threshold_max) + float(resolved_cfg.threshold_step) / 2.0,
            float(resolved_cfg.threshold_step),
        ),
        6,
    ).tolist()

    edge_frame_top1 = prepare_edge_frame(
        df_eval,
        prob_col="p_win_platt_shift",
        odds_col=resolved_cfg.calibration_odds_col,
        label_col="y_true",
        realized_payout_col="real_return",
    )
    strategy_summary_top1, strategy_details_top1 = simulate_edge_thresholds(
        edge_frame_top1,
        thresholds=thresholds,
        selection_mode="top_n_per_race",
        top_n=1,
        stake_mode="flat",
        stake=1.0,
    )
    strategy_summary_top1.insert(0, "variant", "platt_shift_top1")

    strategy_summary_top1.to_csv(STRATEGY_SUMMARY_TOP1_PATH, index=False)
    strategy_details_top1.to_csv(STRATEGY_DETAILS_TOP1_PATH, index=False)
    print(f"saved top1 strategy summary: {STRATEGY_SUMMARY_TOP1_PATH.resolve()}")
    print(f"saved top1 strategy details: {STRATEGY_DETAILS_TOP1_PATH.resolve()}")
    return edge_frame_top1, strategy_details_top1, strategy_summary_top1


@app.cell
def _(mo, strategy_summary_top1):
    # Show the edge-threshold simulation summary table.
    strategy_summary_view = mo.vstack(
        [
            mo.md("Top1 strategy summary"),
            mo.ui.table(strategy_summary_top1),
        ]
    )
    strategy_summary_view
    return


@app.cell
def _(edge_frame_top1, mo, strategy_details_top1):
    # Explain the edge calculation and surface sample bet records.
    explanation_view = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "見方:",
                        f"- 対象候補数: `{len(edge_frame_top1)}`",
                        "- `edge = p_win_platt_shift - 0.8 / odds`",
                        "- 各 threshold で `edge >= threshold` の race top1 のみ購入",
                        "- `n_bets` が少なすぎる閾値は ROI のぶれが大きいので注意",
                    ]
                )
            ),
            mo.md("Top1 strategy details (head 50)"),
            mo.ui.table(strategy_details_top1.head(50)),
        ]
    )
    explanation_view
    return


@app.cell
def _(mo, pd, strategy_summary_top1):
    # Show threshold-by-threshold ROI as a sortable table instead of a plot.
    strategy_threshold_table = strategy_summary_top1.copy()
    strategy_threshold_table["roi_pct"] = (
        pd.to_numeric(strategy_threshold_table["roi"], errors="coerce") * 100.0
    )
    strategy_threshold_table["hit_rate_pct"] = (
        pd.to_numeric(strategy_threshold_table["hit_rate"], errors="coerce") * 100.0
    )
    strategy_threshold_table = strategy_threshold_table[
        [
            "threshold",
            "n_bets",
            "roi",
            "roi_pct",
            "hit_rate",
            "hit_rate_pct",
            "avg_edge",
            "total_stake",
            "total_return",
            "total_profit",
        ]
    ].sort_values("threshold").reset_index(drop=True)

    strategy_table_view = mo.vstack(
        [
            mo.md("Threshold ROI table"),
            mo.ui.table(strategy_threshold_table),
        ]
    )
    strategy_table_view
    return


@app.cell
def _():
    # Import edge simulation helpers used by the purchase strategy cells.
    from harp.core.inference import prepare_edge_frame, simulate_edge_thresholds

    return prepare_edge_frame, simulate_edge_thresholds


@app.cell(hide_code=True)
def _(mo):
    # Introduce optional artifact export using the notebook save use case.
    _section_view = mo.md(
        """
        ## 8. Artifact 保存

        必要なときだけ `save_artifact` を有効にして、base model + Platt payload を保存します。
        race ごとの `logit shift` は推論時に動的計算する前提なので、artifact には post-process の方針だけ残します。
        UseCase 経由で manifest も同時に出します。
        """
    )
    _section_view
    return


@app.cell
def _(lambda_df, mo, race_sum_df):
    # Surface race-level lambda summaries and probability-sum diagnostics.
    race_sum_summary = (
        race_sum_df.loc[:, ["raw_sum", "platt_sum", "shifted_sum"]]
        .describe()
        .reset_index()
    )
    diagnostics_view = mo.vstack(
        [
            mo.md("Race sum summary"),
            mo.ui.table(race_sum_summary),
            mo.md("Logit shift lambda by race (head 30)"),
            mo.ui.table(lambda_df.head(30)),
        ]
    )
    diagnostics_view
    return


@app.cell
def _(mo, resolved_cfg):
    # Surface the current artifact save configuration in the UI.
    artifact_config_view = mo.vstack(
        [
            mo.md(f"- enabled: `{resolved_cfg.save_artifact}`"),
            mo.md(f"- artifact: `{resolved_cfg.artifact_path}`"),
            mo.md(f"- manifest: `{resolved_cfg.manifest_path}`"),
        ]
    )
    artifact_config_view
    return


@app.cell
def _(
    ds,
    metrics_df,
    platt_info,
    resolved_cfg,
    resolved_save_artifact,
    result,
):
    # Save the trained model and manifest only when explicitly requested.
    if not resolved_save_artifact:
        artifact_save_result = None
    else:
        from harp.adapters.driven.storage import (
            JsonManifestStoreAdapter,
            LocalFileGatewayAdapter,
            PickleArtifactStoreAdapter,
        )
        from harp.usecase import (
            NotebookModelArtifactSaveDeps,
            NotebookModelArtifactSaveRequest,
            run_export_notebook_model_artifact_usecase,
        )
        final_metrics = (
            metrics_df.loc[metrics_df["variant"] == "logit_shift", ["auc", "brier", "logloss"]]
            .iloc[0]
            .to_dict()
        )

        _payload = {
            "model": result.model,
            "model_type": "win_platt",
            "feature_names": ds.feature_names,
            "cat_features": ds.cat_features,
            "split_info": ds.split_info,
            "metrics": final_metrics,
            "note": "track4 win platt notebook model with place_v1 features + race logit shift",
            "calibration": {
                "method": "platt_logodds",
                "params": platt_info,
            },
            "post_process": {
                "method": "race_logit_shift",
                "target_sum_per_race": 1.0,
            },
        }
        file_gateway = LocalFileGatewayAdapter()
        artifact_save_result = run_export_notebook_model_artifact_usecase(
            req=NotebookModelArtifactSaveRequest(
                payload=_payload,
                model_type="win_platt",
                artifact_out=resolved_cfg.artifact_path,
                manifest_out=resolved_cfg.manifest_path,
                feature_names=list(ds.feature_names),
                cat_features=list(ds.cat_features),
                train_year_start=int(ds.split_info["train_year_start"]),
                train_year_end=int(ds.split_info["train_year_end"]),
                test_year=int(ds.split_info["test_year"]),
                metrics=final_metrics,
                source_table="mart.m_train_race_horse_past5",
                note="track4 win platt notebook model with place_v1 features + race logit shift",
                calibration_method="platt_logodds",
            ),
            deps=NotebookModelArtifactSaveDeps(
                artifact_store_port=PickleArtifactStoreAdapter(file_gateway=file_gateway),
                manifest_store_port=JsonManifestStoreAdapter(file_gateway=file_gateway),
            ),
        )
    return (artifact_save_result,)


@app.cell
def _(artifact_save_result, mo):
    # Display the artifact export result when the save path is enabled.
    if artifact_save_result is None:
        artifact_result_view = mo.md("Artifact save: pending")
    else:
        artifact_result_view = mo.md(
            "\n".join(
                [
                    "Artifact save: completed",
                    f"- artifact: `{artifact_save_result.artifact_out}`",
                    f"- manifest: `{artifact_save_result.manifest_out}`",
                ]
            )
        )
    artifact_result_view
    return


if __name__ == "__main__":
    app.run()
