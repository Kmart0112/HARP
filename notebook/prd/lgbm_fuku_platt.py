import marimo

__generated_with = "0.23.6"
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
    )


@app.cell
def _(mo):
    _title_md = (
        "# LightGBM複勝版（Platt calibration + marimo最適化）\n\n"
        "- parquet を読み込み\n"
        "- Platt校正で `p_place` を補正\n"
        "- 重い診断（戦略シミュレーション/オッズ帯診断）は明示トグル実行"
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
    POST_PLATT_OUTPUT_DIR = OUTPUT_DIR / "post_platt"
    POST_PLATT_ARTIFACT_DIR = POST_PLATT_OUTPUT_DIR / "artifacts"
    POST_PLATT_METADATA_DIR = POST_PLATT_OUTPUT_DIR / "metadata"
    MODEL_EVAL_LOG_PATH = POST_PLATT_OUTPUT_DIR / "model_eval_log.csv"

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
    POST_PLATT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    POST_PLATT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    POST_PLATT_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    notebook_feature_config = NotebookFeatureConfigController(load_pipeline_runtime_config())
    return (
        CACHE_DIR,
        MODEL_EVAL_LOG_PATH,
        OUTPUT_DIR,
        POST_PLATT_ARTIFACT_DIR,
        POST_PLATT_METADATA_DIR,
        build_notebook_config,
        dataframe_cache_exists,
        notebook_feature_config,
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
        fukusho_type: str = Field(default="j_odds_fukusho_avg")
        global_seed: int = Field(default=42)
        main_parquet_path: str = Field(default="")
        odds_parquet_path: str = Field(default="")
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        run_advanced_default: bool = Field(default=False)

    cfg = RunConfig()
    return (cfg,)


@app.cell
def _(cfg, mo):
    feature_set_name_widget = mo.ui.text(
        label="Feature set name",
        value=cfg.feature_set_name,
        placeholder="place_v1",
        full_width=True,
    )
    registry_path_widget = mo.ui.text(
        label="Registry path",
        value=cfg.registry_path,
        placeholder="pipeline/config/feature_registry.yml",
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
    run_advanced_switch = mo.ui.switch(
        value=cfg.run_advanced_default,
        label="Run advanced diagnostics",
    )

    _settings_view = mo.vstack(
        [
            mo.md("## 実行設定"),
            feature_set_name_widget,
            registry_path_widget,
            main_parquet_path_widget,
            odds_parquet_path_widget,
            mo.hstack([run_advanced_switch]),
            mo.md("- `Run advanced diagnostics` OFF: 重い診断をスキップ"),
        ]
    )
    _settings_view
    return (
        feature_set_name_widget,
        main_parquet_path_widget,
        odds_parquet_path_widget,
        registry_path_widget,
        run_advanced_switch,
    )


@app.cell
def _(
    CACHE_DIR,
    build_notebook_config,
    cfg,
    feature_set_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    mo,
    odds_parquet_path_widget,
    registry_path_widget,
    run_advanced_switch,
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
        }
    )

    if not resolved_cfg.feature_set_name:
        raise ValueError("feature_set_name is required.")
    resolved_run_advanced = bool(resolved_cfg.run_advanced_default)
    return resolved_cfg, resolved_run_advanced


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
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    resolved_cfg,
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
    resolved_cfg,
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
def _(
    build_binary_dataset,
    cat_features,
    df_main,
    feature_names,
    np,
    pd,
    resolved_cfg,
):
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
        target_col="is_place",
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
def _(ODDS_COL, df_odds, df_test_keys, ds, model, pd, resolved_cfg):
    _pred_test = model.predict_proba(ds.X_test)[:, 1]

    _df_test = df_test_keys.copy()
    _df_test["y_true"] = ds.y_test.astype(int).values
    _df_test["p_place"] = _pred_test.astype(float)

    _odds_cols = [
        "race_id",
        "horse_number",
        "odds_fukusho_low",
        "odds_fukusho_high",
        "odds_fukusho_avg",
        "odds_fukusho_weighted_avg",
        "pay_fukusho",
        "j_odds_tansho",
        "j_odds_fukusho_low",
        "j_odds_fukusho_high",
        "j_odds_fukusho_avg",
        "j_odds_fukusho_weighted_avg",
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
        df_eval_raw[str(resolved_cfg.fukusho_type)], errors="coerce"
    ).astype(float)

    df_eval_raw = df_eval_raw.dropna(subset=[ODDS_COL]).copy()
    df_eval_raw["real_return_actual"] = (
        pd.to_numeric(df_eval_raw["pay_fukusho"], errors="coerce").fillna(0.0) / 100.0
    )
    df_eval_raw["real_return"] = df_eval_raw["real_return_actual"]
    df_eval_raw["real_profit"] = df_eval_raw["real_return"] - 1.0
    df_eval_raw["ev_return"] = df_eval_raw["p_place"] * df_eval_raw[ODDS_COL]
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
    np,
    pd,
    resolved_cfg,
):
    from harp.core.training import apply_platt_logodds, fit_platt_logodds_oof

    platt_odds_col = PLATT_ODDS_COL_DEFAULT
    if platt_odds_col not in df_feat.columns:
        platt_odds_col = str(resolved_cfg.fukusho_type)
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
    _oof_path = OUTPUT_DIR / "oof_fold_metrics.csv"
    fold_log_df.to_csv(_oof_path, index=False)
    print(f"saved OOF fold metrics: {_oof_path.resolve()}")

    _payload = {
        "calibration": {
            "method": "platt_logodds",
            "params": platt_info,
        }
    }
    _p_base = (
        pd.to_numeric(df_eval_raw["p_place"], errors="coerce")
        .fillna(0.0)
        .astype(float)
        .clip(0.0, 1.0)
    )

    df_eval = df_eval_raw.copy()
    df_eval["p_place_raw"] = _p_base
    df_eval["p_place_platt"] = apply_platt_logodds(
        base_proba=_p_base.to_numpy(),
        payload=_payload,
        df_feat=df_eval,
        odds_col=platt_odds_col,
    )
    df_eval["p_place"] = df_eval["p_place_platt"].astype(float)
    df_eval["ev_return"] = df_eval["p_place"] * df_eval[ODDS_COL]
    df_eval["ev_profit"] = df_eval["ev_return"] - 1.0

    _coef = np.asarray(platt_info.get("platt", {}).get("coef", [1.0, 0.0]), dtype=float)
    _intercept_arr = np.asarray(
        platt_info.get("platt", {}).get("intercept", [0.0]), dtype=float
    )
    _intercept = float(_intercept_arr[0]) if _intercept_arr.size else 0.0

    class _PlattLogOddsModel:
        def __init__(self, coef_vec: np.ndarray, intercept_val: float):
            self.coef_ = np.asarray(coef_vec, dtype=float).reshape(1, -1)
            self.intercept_ = np.asarray([intercept_val], dtype=float)

        def predict_proba(self, X: np.ndarray) -> np.ndarray:
            _X = np.asarray(X, dtype=float)
            if _X.ndim != 2 or _X.shape[1] != 2:
                raise ValueError(f"X shape must be (n_samples, 2), got: {_X.shape}")
            _logits = _X @ self.coef_.reshape(-1) + float(self.intercept_[0])
            _logits = np.clip(_logits, -50.0, 50.0)
            _p = 1.0 / (1.0 + np.exp(-_logits))
            return np.column_stack([1.0 - _p, _p])

    platt_lr = _PlattLogOddsModel(coef_vec=_coef, intercept_val=_intercept)
    print("Platt coef:", platt_lr.coef_)
    print("Platt intercept:", platt_lr.intercept_)
    return df_eval, platt_info, platt_lr


@app.cell
def _(mo):
    _section_md = "## メトリクス評価とログ保存"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(
    MODEL_EVAL_LOG_PATH,
    brier_score_loss,
    datetime,
    df_eval,
    json,
    log_loss,
    model_params,
    pd,
    resolved_cfg,
    roc_auc_score,
):
    _y_true = df_eval["y_true"].astype(int).to_numpy()
    _pred = df_eval["p_place"].astype(float).to_numpy()
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
        "fukusho_type": str(resolved_cfg.fukusho_type),
        "model_params": json.dumps(model_params, ensure_ascii=False),
    }

    _out_path = MODEL_EVAL_LOG_PATH
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
def _(mo):
    _section_md = "## Artifact Save"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(POST_PLATT_ARTIFACT_DIR, POST_PLATT_METADATA_DIR):
    DEFAULT_ARTIFACT_OUT = POST_PLATT_ARTIFACT_DIR / "is_place_platt_logodds_notebook_v1.pkl"
    DEFAULT_MANIFEST_OUT = POST_PLATT_METADATA_DIR / "is_place_platt_logodds_notebook_v1.json"
    return DEFAULT_ARTIFACT_OUT, DEFAULT_MANIFEST_OUT


@app.cell
def _(DEFAULT_ARTIFACT_OUT, DEFAULT_MANIFEST_OUT, mo):
    save_artifact_button = mo.ui.run_button(label="Save artifact")

    _save_view = mo.vstack(
        [
            mo.md("学習済み base model + platt payload を notebook 専用 artifact/manifest に保存"),
            mo.md(f"- artifact: `{DEFAULT_ARTIFACT_OUT.as_posix()}`"),
            mo.md(f"- manifest: `{DEFAULT_MANIFEST_OUT.as_posix()}`"),
            save_artifact_button,
        ]
    )
    _save_view
    return (save_artifact_button,)


@app.cell
def _(save_artifact_button):
    should_save_artifact = bool(save_artifact_button.value)
    return (should_save_artifact,)


@app.cell
def _(
    DEFAULT_ARTIFACT_OUT,
    DEFAULT_MANIFEST_OUT,
    ds,
    eval_scores,
    model,
    platt_info,
    should_save_artifact,
):
    if not should_save_artifact:
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

        _payload = {
            "model": model,
            "model_type": "place_platt",
            "feature_names": ds.feature_names,
            "cat_features": ds.cat_features,
            "split_info": ds.split_info,
            "metrics": eval_scores,
            "note": "track4 place platt notebook model",
            "calibration": {
                "method": "platt_logodds",
                "params": platt_info,
            },
        }
        _file_gateway = LocalFileGatewayAdapter()
        artifact_save_result = run_export_notebook_model_artifact_usecase(
            req=NotebookModelArtifactSaveRequest(
                payload=_payload,
                model_type="place_platt",
                artifact_out=DEFAULT_ARTIFACT_OUT.as_posix(),
                manifest_out=DEFAULT_MANIFEST_OUT.as_posix(),
                feature_names=ds.feature_names,
                cat_features=ds.cat_features,
                train_year_start=int(ds.split_info["train_year_start"]),
                train_year_end=int(ds.split_info["train_year_end"]),
                test_year=int(ds.split_info["test_year"]),
                metrics=eval_scores,
                source_table="mart.m_train_race_horse_past5",
                note="track4 place platt notebook model",
                calibration_method="platt_logodds",
            ),
            deps=NotebookModelArtifactSaveDeps(
                artifact_store_port=PickleArtifactStoreAdapter(file_gateway=_file_gateway),
                manifest_store_port=JsonManifestStoreAdapter(file_gateway=_file_gateway),
            ),
        )
    return (artifact_save_result,)


@app.cell
def _(artifact_save_result, mo):
    if artifact_save_result is None:
        _artifact_save_view = mo.md("Artifact save: pending")
    else:
        _artifact_save_view = mo.md(
            "\n".join(
                [
                    "Artifact save: completed",
                    f"- artifact: `{artifact_save_result.artifact_out}`",
                    f"- manifest: `{artifact_save_result.manifest_out}`",
                ]
            )
        )
    _artifact_save_view
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

    _imp_path = OUTPUT_DIR / "feature_importance.csv"
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
        df_eval["p_place"]
        .describe()
        .rename_axis("metric")
        .reset_index(name="value")
    )
    _desc_table = mo.ui.table(_desc)
    _desc_view = mo.vstack([mo.md("`p_place` summary"), _desc_table])
    _desc_view
    return


@app.cell
def _(calibration_curve, df_eval, pd):
    _df_cal = df_eval[["p_place", "y_true"]].dropna().copy()
    _df_cal["p_place"] = _df_cal["p_place"].astype(float).clip(0.0, 1.0)
    _df_cal["y_true"] = _df_cal["y_true"].astype(int)

    n_bins = 10
    _df_cal["decile"] = pd.qcut(
        _df_cal["p_place"], q=n_bins, labels=False, duplicates="drop"
    )
    decile_table = (
        _df_cal.groupby("decile")
        .agg(
            n=("y_true", "size"),
            p_mean=("p_place", "mean"),
            y_rate=("y_true", "mean"),
            p_min=("p_place", "min"),
            p_max=("p_place", "max"),
        )
        .reset_index()
        .sort_values("decile")
    )

    _prob_true, _prob_pred = calibration_curve(
        _df_cal["y_true"].values,
        _df_cal["p_place"].values,
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
    _ax.set_xlabel("mean predicted p_place")
    _ax.set_ylabel("observed place rate")
    _ax.grid(True, linewidth=0.4, alpha=0.4)
    _ax.legend()
    _calib_plot_view = mo.vstack([mo.md("Calibration curve"), _fig])
    _calib_plot_view
    return


@app.cell
def _(mo):
    _section_md = "## Advanced diagnostics"
    _section_view = mo.md(_section_md)
    _section_view
    return


@app.cell
def _(mo, resolved_run_advanced):
    if resolved_run_advanced:
        advanced_notice = mo.md("Advanced diagnostics: ON")
    else:
        advanced_notice = mo.md(
            "Advanced diagnostics: OFF（戦略シミュレーションとオッズ帯診断をスキップ）"
        )
    advanced_notice
    return


@app.cell
def _(ODDS_COL, np, pd):
    from harp.core.inference import prepare_edge_frame, simulate_edge_thresholds

    def simulate_kelly_top2_block_rebalance(
        df: pd.DataFrame,
        *,
        edge_th: float = 0.16,
        kelly_fraction: float = 0.1,
        block_size: int = 30,
        initial_bankroll: float = 1.0,
        max_bets_per_race: int = 2,
        per_bet_max_frac: float = 0.05,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        _df = prepare_edge_frame(
            df,
            prob_col="p_place",
            odds_col=ODDS_COL,
            label_col="y_true",
            ev_profit_col="ev_profit",
            realized_payout_col="real_return",
        )
        _race_ids = (
            _df[["race_id"]]
            .drop_duplicates("race_id")
            .sort_values(["race_id"], ascending=[True])["race_id"]
            .tolist()
        )

        _bankroll = float(initial_bankroll)
        _block_base = float(initial_bankroll)
        _bet_rows: list[dict] = []
        _race_rows: list[dict] = []

        for _i, _rid in enumerate(_race_ids):
            if _bankroll <= 0:
                break

            if _i % int(block_size) == 0:
                _block_base = _bankroll

            _race_df = _df[_df["race_id"] == _rid].copy()
            _cand = _race_df[_race_df["edge"].astype(float) >= float(edge_th)].copy()

            if len(_cand) == 0:
                _race_rows.append(
                    {
                        "race_i": int(_i),
                        "race_id": _rid,
                        "bankroll_before": float(_bankroll),
                        "n_bets": 0,
                        "stake": 0.0,
                        "return": 0.0,
                        "profit": 0.0,
                        "bankroll_after": float(_bankroll),
                    }
                )
                continue

            _cand = (
                _cand.sort_values(["edge", "prob"], ascending=[False, False])
                .head(int(max_bets_per_race))
                .reset_index(drop=True)
            )

            _mult_plan = _cand["payout_mult_plan"].astype(float).to_numpy().clip(min=1e-12)
            _prob = _cand["prob"].astype(float).to_numpy().clip(min=0.0, max=1.0)
            _b = np.clip(_mult_plan - 1.0, 1e-12, None)
            _f = (_prob * _mult_plan - 1.0) / _b
            _f = np.nan_to_num(_f, nan=0.0, posinf=0.0, neginf=0.0).clip(min=0.0)

            _stake_raw = _block_base * float(kelly_fraction) * _f
            _bankroll_before = _bankroll
            _bet_cap = _bankroll_before * float(per_bet_max_frac)
            _stake_raw = np.minimum(_stake_raw, _bet_cap)

            _total_raw = float(np.sum(_stake_raw))
            if (_total_raw > 0.0) and (_total_raw > _bankroll_before):
                _stake = _stake_raw * (_bankroll_before / _total_raw)
            else:
                _stake = _stake_raw
            _stake = np.clip(_stake, 0.0, None)

            _mult_real = _cand["payout_mult_real"].astype(float).to_numpy()
            _y = _cand["y"].astype(int).to_numpy()
            _ret = np.where(_y == 1, _stake * _mult_real, 0.0)
            _profit = _ret - _stake

            _race_stake = float(np.sum(_stake))
            _race_return = float(np.sum(_ret))
            _race_profit = float(np.sum(_profit))
            _bankroll = _bankroll_before + _race_profit

            for _j in range(len(_cand)):
                _bet_rows.append(
                    {
                        "race_i": int(_i),
                        "race_id": _rid,
                        "stake": float(_stake[_j]),
                        "prob": float(_prob[_j]),
                        "edge": float(_cand.loc[_j, "edge"]),
                        "odds": float(_mult_plan[_j]),
                        "y": int(_y[_j]),
                        "return": float(_ret[_j]),
                        "profit": float(_profit[_j]),
                    }
                )

            _race_rows.append(
                {
                    "race_i": int(_i),
                    "race_id": _rid,
                    "bankroll_before": float(_bankroll_before),
                    "n_bets": int(len(_cand)),
                    "stake": _race_stake,
                    "return": _race_return,
                    "profit": _race_profit,
                    "bankroll_after": float(_bankroll),
                }
            )

        _bet_detail = pd.DataFrame(_bet_rows)
        _race_curve = pd.DataFrame(_race_rows)
        _total_stake = float(_bet_detail["stake"].sum()) if len(_bet_detail) else 0.0
        _total_return = float(_bet_detail["return"].sum()) if len(_bet_detail) else 0.0
        _summary = pd.Series(
            {
                "initial_bankroll": float(initial_bankroll),
                "final_bankroll": float(_bankroll),
                "bankroll_multiple": (
                    float(_bankroll / float(initial_bankroll))
                    if float(initial_bankroll) != 0.0
                    else np.nan
                ),
                "n_races": int(_race_curve.shape[0]),
                "n_bets": int(_bet_detail.shape[0]),
                "total_stake": _total_stake,
                "total_return": _total_return,
                "total_profit": float(_total_return - _total_stake),
                "roi": float(_total_return / _total_stake) if _total_stake > 0 else np.nan,
                "hit_rate": float(_bet_detail["y"].mean()) if len(_bet_detail) else np.nan,
            }
        )
        return _race_curve, _bet_detail, _summary

    return (
        prepare_edge_frame,
        simulate_edge_thresholds,
        simulate_kelly_top2_block_rebalance,
    )


@app.cell
def _(
    df_eval,
    log_loss,
    np,
    pd,
    platt_lr,
    prepare_edge_frame,
    resolved_run_advanced,
):
    if not resolved_run_advanced:
        noise_res = pd.DataFrame()
        noise_summary_dp = pd.DataFrame()
        noise_summary_ll = pd.DataFrame()
    else:
        _eps = 1e-12
        _sigmas = [0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
        _n_mc = 30
        _seed = 42

        _df_noise_base = prepare_edge_frame(
            df_eval,
            prob_col="p_place_raw",
            odds_col="j_odds_tansho" if "j_odds_tansho" in df_eval.columns else "odds",
            label_col="y_true",
            ev_profit_col="ev_profit",
            realized_payout_col="real_return",
        )
        _odds_col = "j_odds_tansho" if "j_odds_tansho" in _df_noise_base.columns else "odds"

        _df_noise = _df_noise_base[["race_id", "y_true", "p_place_raw", _odds_col]].copy()
        _df_noise["race_id"] = _df_noise["race_id"].astype(str)
        _df_noise["y_true"] = _df_noise["y_true"].astype(int)

        _p_raw = pd.to_numeric(_df_noise["p_place_raw"], errors="coerce").fillna(0.0).astype(float)
        _race = _df_noise["race_id"]
        _sum_p = _p_raw.groupby(_race).transform("sum").astype(float)
        _n_p = _p_raw.groupby(_race).transform("size").astype(float)
        _p_base = np.where(_sum_p > 0, (_p_raw / _sum_p).to_numpy(), (1.0 / _n_p).to_numpy())
        _p_base = np.clip(_p_base, 0.0, 1.0)

        _odds_base = pd.to_numeric(_df_noise[_odds_col], errors="coerce").astype(float)
        _odds_base = _odds_base.fillna(_odds_base.median()).clip(lower=_eps).to_numpy()
        _log_odds_base = np.log(_odds_base)

        def _logit_local(arr: np.ndarray) -> np.ndarray:
            _arr = np.clip(arr, _eps, 1.0 - _eps)
            return np.log(_arr / (1.0 - _arr))

        def _prob_diff_stats(delta: np.ndarray) -> dict:
            _delta = np.asarray(delta, dtype=float)
            _abs_delta = np.abs(_delta)
            return {
                "dp_mean": float(np.mean(_delta)),
                "dp_std": float(np.std(_delta)),
                "dp_abs_mean": float(np.mean(_abs_delta)),
                "dp_abs_p95": float(np.quantile(_abs_delta, 0.95)),
                "dp_abs_p99": float(np.quantile(_abs_delta, 0.99)),
                "dp_abs_max": float(np.max(_abs_delta)),
            }

        _X_base = np.column_stack([_logit_local(_p_base), _log_odds_base])
        _p_platt_base = platt_lr.predict_proba(_X_base)[:, 1].astype(float)
        _ll_platt_base = float(log_loss(_df_noise["y_true"].values, np.clip(_p_platt_base, _eps, 1 - _eps)))

        _p_imp_raw = (1.0 / np.clip(_odds_base, _eps, None)).astype(float)
        _sum_imp = pd.Series(_p_imp_raw).groupby(_race).transform("sum").astype(float)
        _n_imp = pd.Series(_p_imp_raw).groupby(_race).transform("size").astype(float)
        _p_imp_base = np.where(_sum_imp > 0, (_p_imp_raw / _sum_imp), (1.0 / _n_imp))
        _p_imp_base = np.clip(_p_imp_base, 0.0, 1.0)
        _ll_mkt_base = float(log_loss(_df_noise["y_true"].values, np.clip(_p_imp_base, _eps, 1 - _eps)))

        _rng = np.random.default_rng(_seed)
        _rows = []
        _y = _df_noise["y_true"].values

        for _sigma in _sigmas:
            for _trial in range(_n_mc):
                if _sigma == 0.0:
                    _log_odds_noisy = _log_odds_base.copy()
                else:
                    _log_odds_noisy = _log_odds_base + _rng.normal(
                        loc=0.0,
                        scale=float(_sigma),
                        size=_log_odds_base.shape[0],
                    )

                _X_noisy = np.column_stack([_logit_local(_p_base), _log_odds_noisy])
                _p_platt_noisy = platt_lr.predict_proba(_X_noisy)[:, 1].astype(float)
                _ll_platt_noisy = float(log_loss(_y, np.clip(_p_platt_noisy, _eps, 1 - _eps)))

                _odds_noisy = np.exp(_log_odds_noisy).clip(min=_eps)
                _p_imp_noisy_raw = (1.0 / _odds_noisy).astype(float)
                _sum_imp_noisy = pd.Series(_p_imp_noisy_raw).groupby(_race).transform("sum").astype(float)
                _n_imp_noisy = pd.Series(_p_imp_noisy_raw).groupby(_race).transform("size").astype(float)
                _p_imp_noisy = np.where(
                    _sum_imp_noisy > 0,
                    (_p_imp_noisy_raw / _sum_imp_noisy),
                    (1.0 / _n_imp_noisy),
                )
                _p_imp_noisy = np.clip(_p_imp_noisy, 0.0, 1.0)
                _ll_mkt_noisy = float(log_loss(_y, np.clip(_p_imp_noisy, _eps, 1 - _eps)))

                _platt_stat = _prob_diff_stats(_p_platt_noisy - _p_platt_base)
                _mkt_stat = _prob_diff_stats(_p_imp_noisy - _p_imp_base)

                _row = {
                    "sigma": float(_sigma),
                    "trial": int(_trial),
                    "logloss_platt": _ll_platt_noisy,
                    "logloss_market": _ll_mkt_noisy,
                    "delta_platt": _ll_platt_noisy - _ll_platt_base,
                    "delta_market": _ll_mkt_noisy - _ll_mkt_base,
                }
                _row.update({f"platt_{_k}": _v for _k, _v in _platt_stat.items()})
                _row.update({f"mkt_{_k}": _v for _k, _v in _mkt_stat.items()})
                _rows.append(_row)

        noise_res = pd.DataFrame(_rows)
        noise_summary_ll = (
            noise_res.groupby("sigma")[["delta_platt", "delta_market"]]
            .agg(["mean", "std"])
            .reset_index()
        )

        _prob_cols = [
            "platt_dp_abs_mean",
            "platt_dp_abs_p95",
            "platt_dp_abs_p99",
            "platt_dp_abs_max",
            "mkt_dp_abs_mean",
            "mkt_dp_abs_p95",
            "mkt_dp_abs_p99",
            "mkt_dp_abs_max",
            "platt_dp_std",
            "mkt_dp_std",
        ]
        _prob_cols = [_col for _col in _prob_cols if _col in noise_res.columns]
        noise_summary_dp = noise_res.groupby("sigma")[_prob_cols].agg(["mean", "std"]).reset_index()
    return noise_summary_dp, noise_summary_ll


@app.cell
def _(mo, noise_summary_dp, noise_summary_ll, plt, resolved_run_advanced):
    if not resolved_run_advanced:
        noise_output = mo.md("Noise sensitivity: skipped")
    else:
        _table_ll = mo.ui.table(noise_summary_ll)
        _table_dp = mo.ui.table(noise_summary_dp)
        _plot_df = noise_summary_ll.copy()
        _sigma = _plot_df["sigma"].to_numpy()
        _platt_mean = _plot_df[("delta_platt", "mean")].to_numpy()
        _mkt_mean = _plot_df[("delta_market", "mean")].to_numpy()

        _fig, _ax = plt.subplots(figsize=(7.0, 4.5))
        _ax.plot(_sigma, _platt_mean, marker="o", label="Platt (uses log-odds)")
        _ax.plot(_sigma, _mkt_mean, marker="o", label="Market (1/odds)")
        _ax.axhline(0.0, color="k", linewidth=1, alpha=0.6)
        _ax.set_xlabel("sigma (noise std on log-odds)")
        _ax.set_ylabel("Δ logloss vs baseline")
        _ax.set_title("Log-odds noise sensitivity")
        _ax.grid(True, linewidth=0.4, alpha=0.4)
        _ax.legend()

        noise_output = mo.vstack(
            [
                mo.md("Noise sensitivity: completed"),
                _table_ll,
                _table_dp,
                _fig,
            ]
        )
    noise_output
    return


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
            prob_col="p_place",
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
        strategy_output = mo.md("Strategy simulation: skipped")
    else:
        _summary_flat = mo.ui.table(strategy_summary_flat)
        _summary_edge = mo.ui.table(strategy_summary_edge)
        _details_flat = mo.ui.table(strategy_details_flat.head(50))
        _details_edge = mo.ui.table(strategy_details_edge.head(50))
        strategy_output = mo.vstack(
            [
                mo.md("Strategy simulation: completed"),
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


@app.cell
def _(
    ODDS_COL,
    calibration_curve,
    df_eval,
    np,
    pd,
    plt,
    resolved_run_advanced,
):
    if not resolved_run_advanced:
        odds_band_fig = None
        odds_band_summary = pd.DataFrame()
    else:
        _labels = ["1-1.4", "1.4-1.8", "1.8-2.5", "2.5-4.0", "4.0-7", "7-10", "10-50", "50+"]
        _bins = [1, 1.4, 1.8, 2.5, 4.0, 7, 10, 50, np.inf]

        _df_band = df_eval[["p_place", "y_true", ODDS_COL]].dropna().copy()
        _df_band["p_place"] = _df_band["p_place"].astype(float).clip(0, 1)
        _df_band["y_true"] = _df_band["y_true"].astype(int)
        _df_band[ODDS_COL] = _df_band[ODDS_COL].astype(float)
        _df_band["odds_band"] = pd.cut(
            _df_band[ODDS_COL],
            bins=_bins,
            labels=_labels,
            right=False,
            include_lowest=True,
        )

        odds_band_fig, _ax = plt.subplots(figsize=(7, 7))
        _ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="perfect")

        _min_n = 800
        for _band in _labels:
            _sub = _df_band[_df_band["odds_band"].astype(str) == _band]
            if len(_sub) < _min_n:
                continue
            _prob_true, _prob_pred = calibration_curve(
                _sub["y_true"].values,
                _sub["p_place"].values,
                n_bins=10,
                strategy="quantile",
            )
            _ax.plot(_prob_pred, _prob_true, marker="o", linewidth=1, label=f"{_band} (n={len(_sub)})")

        _ax.set_title("Calibration curve by odds band")
        _ax.set_xlabel("mean predicted p_place")
        _ax.set_ylabel("observed place rate")
        _ax.grid(True, linewidth=0.4, alpha=0.4)
        _ax.legend(fontsize=8)

        odds_band_summary = (
            _df_band.groupby("odds_band", dropna=False)
            .agg(n=("y_true", "size"), p_mean=("p_place", "mean"), y_rate=("y_true", "mean"))
            .reset_index()
        )
        odds_band_summary["gap"] = odds_band_summary["y_rate"] - odds_band_summary["p_mean"]
    return odds_band_fig, odds_band_summary


@app.cell
def _(mo, odds_band_fig, odds_band_summary, resolved_run_advanced):
    if not resolved_run_advanced:
        _odds_band_view = mo.md("Odds-band calibration: skipped")
    else:
        _odds_band_table = mo.ui.table(odds_band_summary)
        _odds_band_items = [
            mo.md("Odds-band calibration: completed"),
            _odds_band_table,
        ]
        if odds_band_fig is not None:
            _odds_band_items.append(odds_band_fig)
        _odds_band_view = mo.vstack(_odds_band_items)
    _odds_band_view
    return


@app.cell
def _(df_eval, pd, resolved_run_advanced, simulate_kelly_top2_block_rebalance):
    if not resolved_run_advanced:
        bet_detail = pd.DataFrame()
        kelly_summary_df = pd.DataFrame()
        race_curve = pd.DataFrame()
    else:
        race_curve, bet_detail, _summary = simulate_kelly_top2_block_rebalance(
            df_eval,
            edge_th=0.15,
            kelly_fraction=0.1,
            block_size=30,
            initial_bankroll=1.0,
            max_bets_per_race=2,
            per_bet_max_frac=0.05,
        )

        kelly_summary_df = (
            _summary.to_frame(name="value")
            .reset_index()
            .rename(columns={"index": "metric"})
        )
    return bet_detail, kelly_summary_df, race_curve


@app.cell
def _(
    bet_detail,
    kelly_summary_df,
    mo,
    plt,
    race_curve,
    resolved_run_advanced,
):
    if not resolved_run_advanced:
        _kelly_view = mo.md("Kelly simulation: skipped")
    else:
        _kelly_summary_table = mo.ui.table(kelly_summary_df)
        _kelly_bet_table = mo.ui.table(bet_detail.head(50))
        _kelly_items = [
            mo.md("Kelly simulation: completed"),
            _kelly_summary_table,
            _kelly_bet_table,
        ]

        if not race_curve.empty:
            _fig, _ax = plt.subplots(figsize=(10, 4))
            _ax.plot(race_curve["race_i"], race_curve["bankroll_after"], label="bankroll")
            _ax.set_title("Bankroll curve (rebalance every 30 races)")
            _ax.set_xlabel("race index")
            _ax.set_ylabel("bankroll")
            _ax.grid(True, alpha=0.3)
            _ax.legend()
            _kelly_items.append(_fig)
        _kelly_view = mo.vstack(_kelly_items)
    _kelly_view
    return


if __name__ == "__main__":
    app.run()
