import marimo

__generated_with = "0.22.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebookで利用する依存を読み込む。
    import json
    import os
    import random
    import re
    import shlex
    import sys
    from datetime import datetime
    from pathlib import Path

    import lightgbm as lgb
    import marimo as mo
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
        re,
        shlex,
        sys,
    )


@app.cell(hide_code=True)
def _(mo):
    # セル概要: notebook のタイトルと目的を表示する。
    mo.md(
        "\n".join(
            [
                "# LGBM Race Condition Split Compare",
                "",
                "- `race_level` を維持したまま、条件別モデル分割で精度差を比較する",
                "- 比較軸は `global base model vs local condition model`",
                "- 1回の実行で1つの分割戦略だけを評価する",
            ]
        )
    )
    return


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトルートと共通 helper を解決する。
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = PROJECT_ROOT / "src"
    NOTEBOOK_ROOT = PROJECT_ROOT / "notebook" / "lab"
    OUTPUT_DIR = NOTEBOOK_ROOT / "tmp" / "condition_split_compare"

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
    from harp.core.training import (
        ConditionSplitSpec,
        condition_experiment_summary_to_frame,
        condition_slice_results_to_frame,
        run_condition_split_experiment,
    )
    from harp.shared.paths import notebook_analysis_cache_dir

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    notebook_feature_config = NotebookFeatureConfigController(load_pipeline_runtime_config())
    return (
        ConditionSplitSpec,
        OUTPUT_DIR,
        build_notebook_config,
        condition_experiment_summary_to_frame,
        condition_slice_results_to_frame,
        dataframe_cache_exists,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        notebook_feature_config,
        resolve_dataframe_cache_path,
        run_condition_split_experiment,
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
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        global_seed: int = Field(default=42)
        main_parquet_path: str = Field(default="")
        feature_set_name: str = Field(default="place_v1")
        registry_path: str = Field(default=notebook_feature_config.default_registry_path())
        output_dir: str = Field(default=str(OUTPUT_DIR))
        condition_column: str = Field(default="distance_m")
        split_mode: str = Field(default="exact")
        bin_edges: str = Field(default="")
        bin_labels: str = Field(default="")
        include_values: str = Field(default="")
        exclude_values: str = Field(default="")
        min_train_rows: int = Field(default=500)
        min_val_rows: int = Field(default=50)
        min_test_rows: int = Field(default=50)
        primary_metric: str = Field(default="logloss")

    cfg = RunConfig()
    return RunConfig, cfg


@app.cell
def _(cfg, mo):
    # セル概要: 実行設定 UI を表示する。
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
        placeholder="Leave blank to use notebook/tmp/analysis_cache default",
        full_width=True,
    )
    output_dir_widget = mo.ui.text(
        label="Output dir",
        value=cfg.output_dir,
        full_width=True,
    )
    condition_column_widget = mo.ui.text(
        label="Condition column",
        value=cfg.condition_column,
        full_width=True,
    )
    split_mode_widget = mo.ui.dropdown(
        options=["exact", "manual_bins"],
        value=cfg.split_mode,
        label="Split mode",
    )
    bin_edges_widget = mo.ui.text(
        label="Bin edges",
        value=cfg.bin_edges,
        placeholder='[0, 1400, 1700, 2100, 10000] or "0,1400,1700,2100,10000"',
        full_width=True,
    )
    bin_labels_widget = mo.ui.text(
        label="Bin labels",
        value=cfg.bin_labels,
        placeholder='["short", "mile", "middle", "long"] or "short,mile,middle,long"',
        full_width=True,
    )
    include_values_widget = mo.ui.text(
        label="Include values",
        value=cfg.include_values,
        placeholder='Optional JSON array or comma-separated values',
        full_width=True,
    )
    exclude_values_widget = mo.ui.text(
        label="Exclude values",
        value=cfg.exclude_values,
        placeholder='Optional JSON array or comma-separated values',
        full_width=True,
    )
    train_year_start_widget = mo.ui.number(
        start=2000,
        step=1,
        value=cfg.train_year_start,
        label="Train year start",
    )
    train_year_end_widget = mo.ui.number(
        start=2000,
        step=1,
        value=cfg.train_year_end,
        label="Train year end",
    )
    test_year_widget = mo.ui.number(
        start=2000,
        step=1,
        value=cfg.test_year,
        label="Test year",
    )
    race_level_min_widget = mo.ui.number(
        start=0,
        step=1,
        value=cfg.race_level_min,
        label="Race level min",
    )
    race_level_max_widget = mo.ui.number(
        start=0,
        step=1,
        value=cfg.race_level_max,
        label="Race level max",
    )
    min_train_rows_widget = mo.ui.number(
        start=0,
        step=10,
        value=cfg.min_train_rows,
        label="Min train rows",
    )
    min_val_rows_widget = mo.ui.number(
        start=0,
        step=10,
        value=cfg.min_val_rows,
        label="Min val rows",
    )
    min_test_rows_widget = mo.ui.number(
        start=0,
        step=10,
        value=cfg.min_test_rows,
        label="Min test rows",
    )
    primary_metric_widget = mo.ui.dropdown(
        options=["logloss", "auc", "brier"],
        value=cfg.primary_metric,
        label="Primary metric",
    )
    run_button = mo.ui.run_button(label="Run comparison")

    mo.vstack(
        [
            mo.md("## 1. 実行設定"),
            feature_set_name_widget,
            registry_path_widget,
            main_parquet_path_widget,
            output_dir_widget,
            mo.hstack([condition_column_widget, split_mode_widget]),
            bin_edges_widget,
            bin_labels_widget,
            include_values_widget,
            exclude_values_widget,
            mo.hstack([train_year_start_widget, train_year_end_widget, test_year_widget]),
            mo.hstack([race_level_min_widget, race_level_max_widget, primary_metric_widget]),
            mo.hstack([min_train_rows_widget, min_val_rows_widget, min_test_rows_widget]),
            run_button,
            mo.md("- `manual_bins` のときだけ `bin_edges` / `bin_labels` を使う。"),
            mo.md("- script mode では button を待たずに自動実行する。"),
        ]
    )
    return (
        bin_edges_widget,
        bin_labels_widget,
        condition_column_widget,
        exclude_values_widget,
        feature_set_name_widget,
        include_values_widget,
        main_parquet_path_widget,
        min_test_rows_widget,
        min_train_rows_widget,
        min_val_rows_widget,
        output_dir_widget,
        primary_metric_widget,
        race_level_max_widget,
        race_level_min_widget,
        registry_path_widget,
        run_button,
        split_mode_widget,
        test_year_widget,
        train_year_end_widget,
        train_year_start_widget,
    )


@app.cell
def _(
    RunConfig,
    bin_edges_widget,
    bin_labels_widget,
    build_notebook_config,
    cfg,
    condition_column_widget,
    exclude_values_widget,
    feature_set_name_widget,
    include_values_widget,
    is_script_mode,
    main_parquet_path_widget,
    min_test_rows_widget,
    min_train_rows_widget,
    min_val_rows_widget,
    mo,
    notebook_analysis_cache_dir,
    output_dir_widget,
    primary_metric_widget,
    race_level_max_widget,
    race_level_min_widget,
    registry_path_widget,
    split_mode_widget,
    test_year_widget,
    train_year_end_widget,
    train_year_start_widget,
):
    # セル概要: UI と CLI の設定値を 1 つの設定オブジェクトへ正規化する。
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
                "bin_edges": str(bin_edges_widget.value).strip(),
                "bin_labels": str(bin_labels_widget.value).strip(),
                "condition_column": str(condition_column_widget.value).strip(),
                "exclude_values": str(exclude_values_widget.value).strip(),
                "feature_set_name": str(feature_set_name_widget.value).strip(),
                "include_values": str(include_values_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "min_test_rows": int(min_test_rows_widget.value),
                "min_train_rows": int(min_train_rows_widget.value),
                "min_val_rows": int(min_val_rows_widget.value),
                "output_dir": str(output_dir_widget.value).strip(),
                "primary_metric": str(primary_metric_widget.value).strip(),
                "registry_path": str(registry_path_widget.value).strip(),
                "race_level_max": int(race_level_max_widget.value),
                "race_level_min": int(race_level_min_widget.value),
                "split_mode": str(split_mode_widget.value).strip(),
                "test_year": int(test_year_widget.value),
                "train_year_end": int(train_year_end_widget.value),
                "train_year_start": int(train_year_start_widget.value),
            },
        )

    resolved_cfg = resolved_cfg.model_copy(
        update={
            "condition_column": str(resolved_cfg.condition_column).strip(),
            "feature_set_name": str(resolved_cfg.feature_set_name).strip(),
            "main_parquet_path": str(resolved_cfg.main_parquet_path).strip()
            or str(
                notebook_analysis_cache_dir()
                / f"m_train_race_horse_past5_{resolved_cfg.train_year_start}_{resolved_cfg.test_year}.parquet"
            ),
            "output_dir": str(resolved_cfg.output_dir).strip(),
            "split_mode": str(resolved_cfg.split_mode).strip(),
            "primary_metric": str(resolved_cfg.primary_metric).strip(),
            "registry_path": str(resolved_cfg.registry_path).strip(),
        }
    )

    if not resolved_cfg.condition_column:
        raise ValueError("condition_column is required.")
    if not resolved_cfg.feature_set_name:
        raise ValueError("feature_set_name is required.")
    if resolved_cfg.train_year_start >= resolved_cfg.train_year_end:
        raise ValueError("train_year_start must be < train_year_end.")
    if resolved_cfg.train_year_end >= resolved_cfg.test_year:
        raise ValueError("train_year_end must be < test_year.")
    if resolved_cfg.race_level_min > resolved_cfg.race_level_max:
        raise ValueError("race_level_min must be <= race_level_max.")
    return (resolved_cfg,)


@app.cell
def _(Path, json, re):
    # セル概要: CLI/UI 文字列を spec 用の型へ変換する helper を定義する。
    def parse_string_values(raw: str) -> tuple[str, ...]:
        text = str(raw).strip()
        if not text:
            return ()
        if text.startswith("["):
            payload = json.loads(text)
            if not isinstance(payload, list):
                raise ValueError("Expected JSON array.")
            values = [str(value).strip() for value in payload]
        else:
            values = [part.strip() for part in text.split(",")]
        return tuple(value for value in values if value)

    def parse_float_values(raw: str) -> tuple[float, ...]:
        text = str(raw).strip()
        if not text:
            return ()
        if text.startswith("["):
            payload = json.loads(text)
            if not isinstance(payload, list):
                raise ValueError("Expected JSON array.")
            values = [float(value) for value in payload]
        else:
            values = [float(part.strip()) for part in text.split(",") if part.strip()]
        return tuple(values)

    def safe_file_stem(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", str(value).strip())
        return safe.strip("_") or "condition_split_compare"

    def resolve_output_dir(path_value: str) -> Path:
        output_dir = Path(path_value).expanduser()
        if not output_dir.is_absolute():
            output_dir = (Path.cwd() / output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    return (
        parse_float_values,
        parse_string_values,
        resolve_output_dir,
        safe_file_stem,
    )


@app.cell
def _(
    ConditionSplitSpec,
    Path,
    parse_float_values,
    parse_string_values,
    resolve_output_dir,
    resolved_cfg,
):
    # セル概要: 実験 spec と主要パスを解決する。
    split_spec = ConditionSplitSpec(
        condition_column=resolved_cfg.condition_column,
        split_mode=resolved_cfg.split_mode,
        bin_edges=parse_float_values(resolved_cfg.bin_edges),
        bin_labels=parse_string_values(resolved_cfg.bin_labels),
        include_values=parse_string_values(resolved_cfg.include_values),
        exclude_values=parse_string_values(resolved_cfg.exclude_values),
        min_train_rows=int(resolved_cfg.min_train_rows),
        min_val_rows=int(resolved_cfg.min_val_rows),
        min_test_rows=int(resolved_cfg.min_test_rows),
        primary_metric=resolved_cfg.primary_metric,
    )
    cache_path = Path(resolved_cfg.main_parquet_path).expanduser()
    output_dir = resolve_output_dir(resolved_cfg.output_dir)
    return cache_path, output_dir, split_spec


@app.cell
def _(np, os, random, resolved_cfg):
    # セル概要: 乱数 seed を固定する。
    os.environ["PYTHONHASHSEED"] = str(resolved_cfg.global_seed)
    random.seed(resolved_cfg.global_seed)
    np.random.seed(resolved_cfg.global_seed)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: データ読み込みセクションの見出しを表示する。
    mo.md("""
    ## 2. データ読み込み
    """)
    return


@app.cell
def _(
    cache_path,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    resolved_cfg,
    shlex,
):
    # セル概要: analysis cache parquet を読み込む。
    if dataframe_cache_exists(cache_path):
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
    return (df,)


@app.cell
def _(notebook_feature_config, resolved_cfg):
    # セル概要: registry から feature_names / cat_features を読み込む。
    _resolved_registry_path, feature_names, cat_features = notebook_feature_config.resolve_feature_set(
        feature_set_name=resolved_cfg.feature_set_name,
        registry_path=resolved_cfg.registry_path,
    )
    return cat_features, feature_names


@app.cell
def _(df, pd, resolved_cfg):
    # セル概要: notebook 側で race_level を明示的に再適用する。
    if "race_level" not in df.columns:
        raise KeyError("race_level column is required in the main parquet.")
    race_level = pd.to_numeric(df["race_level"], errors="coerce")
    if race_level.isna().any():
        raise ValueError("race_level contains invalid values.")
    df_filtered = df.loc[
        (race_level >= int(resolved_cfg.race_level_min))
        & (race_level <= int(resolved_cfg.race_level_max))
    ].copy()
    if df_filtered.empty:
        raise ValueError("0 rows remain after applying race_level filter.")
    return (df_filtered,)


@app.cell
def _(df, df_filtered, mo, resolved_cfg):
    # セル概要: 入力データの基本サマリを表示する。
    mo.md(
        "\n".join(
            [
                "### Input Dataset",
                f"- rows before race_level filter: `{len(df)}`",
                f"- rows after race_level filter: `{len(df_filtered)}`",
                f"- race_level range: `{resolved_cfg.race_level_min}..{resolved_cfg.race_level_max}`",
            ]
        )
    )
    return


@app.cell
def _(is_script_mode, mo, run_button):
    # セル概要: interactive 実行では button 押下まで重い処理を止める。
    mo.stop((not is_script_mode) and (not run_button.value), mo.md("Press `Run comparison` to execute."))
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: モデル実行セクションの見出しを表示する。
    mo.md("""
    ## 3. 条件別比較実行
    """)
    return


@app.cell
def _(lgb, resolved_cfg):
    # セル概要: 学習パラメータを既存 metrics notebook と同じ初期値で定義する。
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
        "n_jobs": 6,
    }
    fit_kwargs = {
        "eval_metric": "binary_logloss",
        "callbacks": [
            lgb.early_stopping(200, verbose=True),
            lgb.log_evaluation(period=50),
        ],
    }
    return fit_kwargs, model_params


@app.cell
def _(
    cat_features,
    condition_experiment_summary_to_frame,
    condition_slice_results_to_frame,
    df_filtered,
    feature_names,
    fit_kwargs,
    model_params,
    pd,
    resolved_cfg,
    run_condition_split_experiment,
    split_spec,
):
    # セル概要: base model と local condition model の比較実験を実行する。
    summary, slice_results = run_condition_split_experiment(
        pd.DataFrame(df_filtered),
        spec=split_spec,
        feature_names=feature_names,
        cat_features=cat_features,
        target_col="is_place",
        train_year_start=resolved_cfg.train_year_start,
        train_year_end=resolved_cfg.train_year_end,
        test_year=resolved_cfg.test_year,
        model_params=model_params,
        fit_kwargs=fit_kwargs,
    )
    summary_df = condition_experiment_summary_to_frame(summary)
    slice_df = condition_slice_results_to_frame(slice_results)
    if not slice_df.empty:
        slice_df = slice_df.sort_values(
            by=["test_rows", "condition_value"],
            ascending=[False, True],
        ).reset_index(drop=True)
    return slice_df, summary, summary_df


@app.cell
def _(mo, resolved_cfg, split_spec, summary):
    # セル概要: 実験の要約を markdown で表示する。
    mo.md(
        "\n".join(
            [
                "### Run Summary",
                f"- condition_column: `{split_spec.condition_column}`",
                f"- split_mode: `{split_spec.split_mode}`",
                f"- primary_metric: `{split_spec.primary_metric}`",
                f"- compared_slices: `{summary.compared_slices}` / total `{summary.total_slices}`",
                f"- skipped_slices: `{summary.skipped_slices}`",
                f"- compared_test_rows: `{summary.compared_test_rows}` / total test rows `{summary.total_test_rows}`",
                f"- weighted base logloss: `{summary.weighted_base_logloss}`",
                f"- weighted local logloss: `{summary.weighted_local_logloss}`",
                f"- weighted delta logloss: `{summary.weighted_delta_logloss}`",
                f"- train/val/test years: `{resolved_cfg.train_year_start}-{resolved_cfg.train_year_end}-{resolved_cfg.test_year}`",
            ]
        )
    )
    return


@app.cell
def _(summary_df):
    # セル概要: summary dataframe を表示する。
    summary_df
    return


@app.cell
def _(slice_df):
    # セル概要: 条件別の比較結果 dataframe を表示する。
    slice_df
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 出力保存セクションの見出しを表示する。
    mo.md("""
    ## 4. CSV 保存
    """)
    return


@app.cell
def _(datetime, output_dir, safe_file_stem, slice_df, split_spec, summary_df):
    # セル概要: summary と condition 別結果を CSV に保存する。
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = safe_file_stem(f"{split_spec.condition_column}_{split_spec.split_mode}_{timestamp}")
    summary_csv_path = output_dir / f"{stem}_summary.csv"
    slice_csv_path = output_dir / f"{stem}_slices.csv"
    summary_df.to_csv(summary_csv_path, index=False)
    slice_df.to_csv(slice_csv_path, index=False)
    return slice_csv_path, summary_csv_path


@app.cell
def _(mo, slice_csv_path, summary_csv_path):
    # セル概要: 保存先を表示する。
    mo.md(
        "\n".join(
            [
                "Saved CSV files:",
                f"- summary: `{summary_csv_path}`",
                f"- slices: `{slice_csv_path}`",
            ]
        )
    )
    return


if __name__ == "__main__":
    app.run()
