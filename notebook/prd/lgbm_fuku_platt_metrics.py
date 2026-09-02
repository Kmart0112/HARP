import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import json
    import os
    import random
    import shlex
    import sys
    from datetime import datetime
    from pathlib import Path

    import lightgbm as lgb
    import numpy as np
    import pandas as pd
    import yaml
    from pydantic import BaseModel, Field

    return (
        BaseModel,
        Field,
        Path,
        datetime,
        json,
        lgb,
        mo,
        np,
        os,
        pd,
        random,
        shlex,
        sys,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # LGBM Place Metrics (marimo + harp.core)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 1. 実行設定
    """)
    return


@app.cell
def _(Path, sys):
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "prd"
    OUTPUT_DIR = NOTEBOOK_ROOT / "outputs"
    ARTIFACT_DIR = OUTPUT_DIR / "artifacts"
    METADATA_DIR = OUTPUT_DIR / "metadata"
    MODEL_EVAL_LOG_PATH = NOTEBOOK_ROOT / "outputs" / "model_eval_log.csv"

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
        METADATA_DIR,
        MODEL_EVAL_LOG_PATH,
        build_notebook_config,
        dataframe_cache_exists,
        notebook_feature_config,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        resolve_dataframe_cache_path,
    )


@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(ARTIFACT_DIR, BaseModel, Field, METADATA_DIR, notebook_feature_config):
    default_artifact_path = str(ARTIFACT_DIR / "is_place_notebook_v1.pkl")
    default_manifest_path = str(METADATA_DIR / "is_place_notebook_v1.json")

    class RunConfig(BaseModel):
        test_year: int = Field(default=2025)
        train_year_start: int = Field(default=2013)
        train_year_end: int = Field(default=2024)
        fukusho_type: str = Field(default="j_odds_fukusho_avg")
        global_seed: int = Field(default=42)
        main_parquet_path: str = Field(default="")
        save_artifact: bool = Field(default=False)
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        resolved_features_config_path: str = Field(default="")
        artifact_path: str = Field(default=default_artifact_path)
        manifest_path: str = Field(default=default_manifest_path)

    cfg = RunConfig()
    return (cfg,)


@app.cell
def _(cfg, mo):
    main_parquet_path_widget = mo.ui.text(
        label="Main parquet path",
        value=cfg.main_parquet_path,
        placeholder="notebook/tmp/analysis_cache/....parquet",
        full_width=True,
    )
    save_artifact_switch = mo.ui.switch(
        value=cfg.save_artifact,
        label="Save artifact",
    )
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
    mo.vstack(
        [
            feature_set_name_widget,
            registry_path_widget,
            mo.md("Set `main_parquet_path` or leave blank to use the default analysis cache path."),
            main_parquet_path_widget,
            mo.hstack([save_artifact_switch]),
            artifact_path_widget,
            manifest_path_widget,
        ]
    )
    return (
        artifact_path_widget,
        feature_set_name_widget,
        main_parquet_path_widget,
        manifest_path_widget,
        registry_path_widget,
        save_artifact_switch,
    )


@app.cell
def _(
    artifact_path_widget,
    build_notebook_config,
    cfg,
    feature_set_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    manifest_path_widget,
    mo,
    notebook_analysis_cache_dir,
    registry_path_widget,
    save_artifact_switch,
):
    if is_script_mode:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            cli_args=mo.cli_args(),
            overrides={"save_artifact": True},
        )
    else:
        resolved_cfg = build_notebook_config(
            type(cfg),
            defaults=cfg,
            overrides={
                "artifact_path": str(artifact_path_widget.value).strip(),
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "manifest_path": str(manifest_path_widget.value).strip(),
                "registry_path": str(registry_path_widget.value).strip(),
                "save_artifact": bool(save_artifact_switch.value),
            },
        )

    resolved_cfg = resolved_cfg.model_copy(
        update={
            "artifact_path": str(resolved_cfg.artifact_path).strip(),
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip()
            or str(
                notebook_analysis_cache_dir()
                / f"m_train_race_horse_past5_{resolved_cfg.train_year_start}_{resolved_cfg.test_year}.parquet"
            ),
            "manifest_path": str(resolved_cfg.manifest_path).strip(),
            "registry_path": str(resolved_cfg.registry_path).strip(),
            "resolved_features_config_path": str(resolved_cfg.resolved_features_config_path).strip(),
            "save_artifact": bool(resolved_cfg.save_artifact),
        }
    )

    resolved_save_artifact = bool(resolved_cfg.save_artifact)

    if not resolved_cfg.feature_set_name and not resolved_cfg.resolved_features_config_path:
        raise ValueError("feature_set_name is required.")
    if not resolved_cfg.main_parquet_path:
        raise ValueError("main_parquet_path is required.")
    if resolved_save_artifact and (not resolved_cfg.artifact_path or not resolved_cfg.manifest_path):
        raise ValueError("artifact_path and manifest_path are required when save_artifact is enabled.")
    return resolved_cfg, resolved_save_artifact


@app.cell
def _(np, os, random, resolved_cfg):
    os.environ["PYTHONHASHSEED"] = str(resolved_cfg.global_seed)
    random.seed(resolved_cfg.global_seed)
    np.random.seed(resolved_cfg.global_seed)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 2. データ読み込み（parquet）
    """)
    return


@app.cell
def _(Path, resolved_cfg):
    cache_path = Path(resolved_cfg.main_parquet_path)
    return (cache_path,)


@app.cell
def _(
    cache_path,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    resolved_cfg,
    shlex,
):
    has_cache = dataframe_cache_exists(cache_path)
    if has_cache:
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading from {cache_source_path}")
        df = load_dataframe_cache(cache_path)
    else:
        export_cmd = " ".join(
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
            f"run_command={export_cmd}"
        )

    df.head(1)
    return (df,)


@app.cell
def _(notebook_feature_config, resolved_cfg):
    from harp.core.training import build_binary_dataset

    _resolved_registry_path, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
        resolved_features_config_path=resolved_cfg.resolved_features_config_path,
    )
    return build_binary_dataset, cat_features, feature_names


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 3. 学習データ作成
    """)
    return


@app.cell
def _(build_binary_dataset, cat_features, df, feature_names, pd, resolved_cfg):
    df_frame = pd.DataFrame(df)
    ds = build_binary_dataset(
        df=df_frame,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_place",
        train_year_start=resolved_cfg.train_year_start,
        train_year_end=resolved_cfg.train_year_end,
        test_year=resolved_cfg.test_year,
    )
    ds.split_info
    return (ds,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 4. モデル学習
    """)
    return


@app.cell
def _(ds, lgb, resolved_cfg):
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
        "random_state": resolved_cfg.global_seed,
        "bagging_seed": resolved_cfg.global_seed,
        "feature_fraction_seed": resolved_cfg.global_seed,
        "data_random_seed": resolved_cfg.global_seed,
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": 6,
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
    return model_params, result


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 5. 評価
    """)
    return


@app.cell
def _(mo, result):
    metrics = result.metrics
    mo.md(
        f"""
        **Metrics**
        - AUC: `{metrics.get("auc")}`
        - Brier: `{metrics.get("brier")}`
        - LogLoss: `{metrics.get("logloss")}`
        """
    )
    return (metrics,)


@app.cell
def _(result):
    result.feature_importance.head(30)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 6. 評価ログ保存
    """)
    return


@app.cell
def _(datetime, ds, json, metrics, model_params):
    def build_metrics_row(run_cfg) -> dict[str, object]:
        return {
            "timestamp": datetime.now().isoformat(),
            "auc": metrics.get("auc"),
            "brier": metrics.get("brier"),
            "logloss": metrics.get("logloss"),
            "n_test": int(len(ds.y_test)),
            "train_year_start": run_cfg.train_year_start,
            "train_year_end": run_cfg.train_year_end,
            "test_year": run_cfg.test_year,
            "fukusho_type": run_cfg.fukusho_type,
            "model_params": json.dumps(model_params, ensure_ascii=False),
        }

    return (build_metrics_row,)


@app.cell
def _(MODEL_EVAL_LOG_PATH, build_metrics_row, pd, resolved_cfg):
    def append_metrics_log(out_path, row) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        log_df = pd.DataFrame([row])
        if out_path.exists():
            existing = pd.read_csv(out_path)
            merged = pd.concat([log_df, existing], ignore_index=True)
        else:
            merged = log_df
        merged.to_csv(out_path, index=False)

    out_path = MODEL_EVAL_LOG_PATH
    row = build_metrics_row(resolved_cfg)
    append_metrics_log(out_path, row)
    print(f"saved eval log: {out_path.resolve()}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 7. Artifact 保存
    """)
    return


@app.cell
def _(mo, resolved_cfg):
    _save_view = mo.vstack(
        [
            mo.md("学習済み base place model を notebook 専用 artifact/manifest に保存"),
            mo.md(f"- enabled: `{resolved_cfg.save_artifact}`"),
            mo.md(f"- artifact: `{resolved_cfg.artifact_path}`"),
            mo.md(f"- manifest: `{resolved_cfg.manifest_path}`"),
        ]
    )
    _save_view
    return


@app.cell
def _(
    ds,
    feature_names,
    metrics,
    resolved_cfg,
    resolved_save_artifact,
    result,
):
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

        payload = {
            "model": result.model,
            "model_type": "place",
            "feature_names": ds.feature_names,
            "cat_features": ds.cat_features,
            "split_info": ds.split_info,
            "metrics": metrics,
            "note": "track4 place notebook metrics-only model",
        }
        file_gateway = LocalFileGatewayAdapter()
        artifact_save_result = run_export_notebook_model_artifact_usecase(
            req=NotebookModelArtifactSaveRequest(
                payload=payload,
                model_type="place",
                artifact_out=resolved_cfg.artifact_path,
                manifest_out=resolved_cfg.manifest_path,
                feature_names=list(feature_names),
                cat_features=ds.cat_features,
                train_year_start=int(ds.split_info["train_year_start"]),
                train_year_end=int(ds.split_info["train_year_end"]),
                test_year=int(ds.split_info["test_year"]),
                metrics=metrics,
                source_table="mart.m_train_race_horse_past5",
                note="track4 place notebook metrics-only model",
                calibration_method="none",
            ),
            deps=NotebookModelArtifactSaveDeps(
                artifact_store_port=PickleArtifactStoreAdapter(file_gateway=file_gateway),
                manifest_store_port=JsonManifestStoreAdapter(file_gateway=file_gateway),
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


if __name__ == "__main__":
    app.run()
