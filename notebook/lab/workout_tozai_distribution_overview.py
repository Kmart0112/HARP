import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebook 全体で使う依存を読み込む。
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel, Field
    from sqlalchemy.exc import SQLAlchemyError

    return BaseModel, Field, Path, SQLAlchemyError, mo, np, pd, plt, sys


@app.cell
def _(Path, sys):
    # セル概要: プロジェクト配下の helper と pure function を解決する。
    project_root = Path(__file__).resolve().parents[2]
    src_root = project_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from harp.controllers import build_notebook_config
    from harp.adapters.driven.db.sql_query_builder import validate_identifier
    from harp.adapters.driven.storage import (
        dataframe_cache_exists,
        load_dataframe_cache,
        save_dataframe_cache,
    )
    from harp.core.modeling.workout_tozai_distribution import (
        DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES,
        build_metric_catalog,
        build_tozai_distribution_summary,
        build_tozai_pairwise_test_summary,
        build_tozai_yearly_summary,
        build_workout_tozai_source_catalog,
        prepare_tozai_distribution_frame,
        resolve_workout_tozai_source_spec,
    )
    from harp.shared.db import read_sql_df
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    runtime_config = load_pipeline_runtime_config()
    return (
        DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES,
        build_metric_catalog,
        build_notebook_config,
        build_tozai_distribution_summary,
        build_tozai_pairwise_test_summary,
        build_tozai_yearly_summary,
        build_workout_tozai_source_catalog,
        cache_dir,
        dataframe_cache_exists,
        load_dataframe_cache,
        prepare_tozai_distribution_frame,
        read_sql_df,
        runtime_config,
        resolve_workout_tozai_source_spec,
        save_dataframe_cache,
        validate_identifier,
    )


@app.cell
def _(mo):
    # セル概要: notebook の目的を表示する。
    mo.md(
        "\n".join(
            [
                "# Workout Tozai Distribution Overview",
                "",
                "- raw staging と downstream mart の両方で `tozai_cd` ごとの時計分布を確認する notebook",
                "- `summary stats` と `hist / ECDF`、`pairwise tests`、`yearly median trend` をまとめて見る",
                "- representative workout に紐づく `wood_tozai_cd` / `hanro_tozai_cd` も同じ流れで見られる",
            ]
        )
    )
    return


@app.cell
def _(mo):
    # セル概要: script mode かどうかを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, runtime_config):
    # セル概要: notebook の設定モデルと既定値を定義する。
    class AppConfig(BaseModel):
        db_url: str = Field(default=runtime_config.database.db_url)
        source_table: str = Field(default="mart_wood_current")
        metric_col: str = Field(default="wood_lap_time_1")
        start_date: str = Field(default="2021-01-01")
        end_date: str = Field(default="2026-12-31")
        main_parquet_path: str = Field(default="")
        use_cache: bool = Field(default=True)
        read_from_db: bool = Field(default=True)
        refresh_db: bool = Field(default=False)
        save_cache: bool = Field(default=False)
        max_test_samples: int = Field(default=100_000)

    cfg = AppConfig()
    return AppConfig, cfg


@app.cell
def _(DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES, cfg, mo):
    # セル概要: データソースと集計条件の UI を表示する。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    source_table_widget = mo.ui.dropdown(
        options=list(DEFAULT_WORKOUT_TOZAI_SOURCE_NAMES),
        value=cfg.source_table,
        label="Source",
    )
    metric_col_widget = mo.ui.text(label="Metric column", value=cfg.metric_col, full_width=True)
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)
    end_date_widget = mo.ui.text(label="End date", value=cfg.end_date)
    main_parquet_path_widget = mo.ui.text(
        label="Main parquet path",
        value=cfg.main_parquet_path,
        placeholder="notebook/tmp/analysis_cache/....parquet",
        full_width=True,
    )
    use_cache_widget = mo.ui.switch(value=cfg.use_cache, label="Use cache")
    read_from_db_widget = mo.ui.switch(value=cfg.read_from_db, label="Read from DB")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_db, label="Force DB refresh")
    save_cache_widget = mo.ui.switch(value=cfg.save_cache, label="Save cache after DB read")
    max_test_samples_widget = mo.ui.number(
        start=1_000,
        stop=500_000,
        step=1_000,
        value=cfg.max_test_samples,
        label="Max test samples / group",
    )
    run_button = mo.ui.run_button(label="Load / Refresh")

    mo.vstack(
        [
            mo.md("## 1. Data Source / Metric"),
            db_url_widget,
            mo.hstack([source_table_widget, metric_col_widget]),
            mo.hstack([start_date_widget, end_date_widget]),
            main_parquet_path_widget,
            mo.hstack([use_cache_widget, read_from_db_widget, refresh_db_widget, save_cache_widget]),
            mo.hstack([max_test_samples_widget]),
            mo.hstack([run_button]),
        ]
    )
    return (
        db_url_widget,
        end_date_widget,
        main_parquet_path_widget,
        max_test_samples_widget,
        metric_col_widget,
        read_from_db_widget,
        refresh_db_widget,
        run_button,
        save_cache_widget,
        source_table_widget,
        start_date_widget,
        use_cache_widget,
    )


@app.cell
def _(
    AppConfig,
    build_notebook_config,
    cfg,
    db_url_widget,
    end_date_widget,
    is_script_mode,
    main_parquet_path_widget,
    max_test_samples_widget,
    metric_col_widget,
    mo,
    read_from_db_widget,
    refresh_db_widget,
    save_cache_widget,
    source_table_widget,
    start_date_widget,
    use_cache_widget,
):
    # セル概要: script / interactive の設定値を単一 config に正規化する。
    if is_script_mode:
        app_cfg = build_notebook_config(AppConfig, defaults=cfg, cli_args=mo.cli_args())
    else:
        app_cfg = build_notebook_config(
            AppConfig,
            defaults=cfg,
            overrides={
                "db_url": str(db_url_widget.value).strip(),
                "end_date": str(end_date_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "max_test_samples": int(max_test_samples_widget.value),
                "metric_col": str(metric_col_widget.value).strip(),
                "read_from_db": bool(read_from_db_widget.value),
                "refresh_db": bool(refresh_db_widget.value),
                "save_cache": bool(save_cache_widget.value),
                "source_table": str(source_table_widget.value),
                "start_date": str(start_date_widget.value).strip(),
                "use_cache": bool(use_cache_widget.value),
            },
        )
    return (app_cfg,)


@app.cell
def _(Path, cache_dir):
    # セル概要: cache path 解決 helper を定義する。
    def resolve_cache_path(app_cfg) -> Path:
        explicit = str(app_cfg.main_parquet_path).strip()
        if explicit:
            return Path(explicit).expanduser()

        table_slug = str(app_cfg.source_table).replace(".", "_")
        metric_slug = str(app_cfg.metric_col).replace(".", "_")
        start_slug = str(app_cfg.start_date).replace("-", "")
        end_slug = str(app_cfg.end_date).replace("-", "")
        return cache_dir / f"{table_slug}_{metric_slug}_{start_slug}_{end_slug}.parquet"

    return (resolve_cache_path,)


@app.cell
def _(
    app_cfg,
    build_metric_catalog,
    build_workout_tozai_source_catalog,
    mo,
    resolve_workout_tozai_source_spec,
):
    # セル概要: 選択中ソースの metadata を表示する。
    source_catalog_df = build_workout_tozai_source_catalog()
    selected_spec = resolve_workout_tozai_source_spec(app_cfg.source_table)
    metric_catalog_df = build_metric_catalog(app_cfg.source_table)
    source_view = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## 2. Source Definition",
                        "",
                        f"- source: `{selected_spec.name}` / `{selected_spec.label}`",
                        f"- physical table: `{selected_spec.table_name}`",
                        f"- group column: `{selected_spec.group_col}`",
                        f"- date column: `{selected_spec.date_col}`",
                        f"- default metric: `{selected_spec.default_metric_col}`",
                    ]
                )
            ),
            mo.md("### Available Sources"),
            source_catalog_df,
            mo.md("### Available Metrics"),
            metric_catalog_df,
        ]
    )
    source_view
    return (selected_spec,)


@app.cell
def _(
    app_cfg,
    dataframe_cache_exists,
    load_dataframe_cache,
    pd,
    read_sql_df,
    resolve_cache_path,
    resolve_workout_tozai_source_spec,
    save_dataframe_cache,
    validate_identifier,
):
    # セル概要: cache or DB から分析用データフレームを取得する helper を定義する。
    _selected_spec = resolve_workout_tozai_source_spec(app_cfg.source_table)

    def _filter_frame(df_source: pd.DataFrame) -> pd.DataFrame:
        work = df_source.copy()
        if _selected_spec.date_col in work.columns:
            work[_selected_spec.date_col] = pd.to_datetime(work[_selected_spec.date_col], errors="coerce")
            if str(app_cfg.start_date).strip():
                work = work.loc[work[_selected_spec.date_col] >= pd.Timestamp(app_cfg.start_date)]
            if str(app_cfg.end_date).strip():
                work = work.loc[work[_selected_spec.date_col] <= pd.Timestamp(app_cfg.end_date)]
        return work.reset_index(drop=True)

    def load_source_dataframe() -> tuple[pd.DataFrame, str]:
        if app_cfg.metric_col not in _selected_spec.metric_cols:
            raise ValueError(
                f"metric_col `{app_cfg.metric_col}` is not available in {_selected_spec.name}. "
                f"available={_selected_spec.metric_cols}"
            )

        cache_path = resolve_cache_path(app_cfg)
        if app_cfg.use_cache and dataframe_cache_exists(cache_path) and not app_cfg.refresh_db:
            return _filter_frame(load_dataframe_cache(cache_path)), f"cache: {cache_path}"

        if not app_cfg.read_from_db:
            raise FileNotFoundError(f"DataFrame cache not found and DB read disabled: {cache_path}")

        table_name = validate_identifier(_selected_spec.table_name, kind="table")
        group_col = validate_identifier(_selected_spec.group_col, kind="column")
        date_col = validate_identifier(_selected_spec.date_col, kind="column")
        metric_col = validate_identifier(app_cfg.metric_col, kind="column")
        sql = f"""
        SELECT {group_col}, {date_col}, {metric_col}
        FROM {table_name}
        WHERE {date_col} >= :start_date
          AND {date_col} <= :end_date
        """
        df_source = read_sql_df(
            sql,
            params={
                "start_date": app_cfg.start_date,
                "end_date": app_cfg.end_date,
            },
            db_url=app_cfg.db_url,
        )
        if app_cfg.save_cache:
            save_dataframe_cache(df_source, cache_path)
        return _filter_frame(df_source), f"db: {table_name}"

    return (load_source_dataframe,)


@app.cell
def _(SQLAlchemyError, is_script_mode, load_source_dataframe, mo, run_button):
    # セル概要: 実データの読み込みを実行し、失敗時は notebook を継続する。
    should_run = is_script_mode or bool(run_button.value)
    if not should_run:
        dataset_df = None
        dataset_error = None
        dataset_source = "idle"
    else:
        try:
            dataset_df, dataset_source = load_source_dataframe()
            dataset_error = None
        except (FileNotFoundError, SQLAlchemyError, ValueError) as exc:
            dataset_df = None
            dataset_source = "unavailable"
            dataset_error = str(exc)

    if dataset_error:
        dataset_status_view = mo.md(f"## 3. Dataset Status\n\n`{dataset_error}`")
    elif dataset_df is None:
        dataset_status_view = mo.md("## 3. Dataset Status\n\n`Load / Refresh` を押すと集計します。")
    else:
        dataset_status_view = mo.md(
            "\n".join(
                [
                    "## 3. Dataset Status",
                    "",
                    f"- source: `{dataset_source}`",
                    f"- rows: `{len(dataset_df):,}`",
                ]
            )
        )
    dataset_status_view
    return (dataset_df,)


@app.cell
def _(
    app_cfg,
    build_tozai_distribution_summary,
    build_tozai_pairwise_test_summary,
    build_tozai_yearly_summary,
    dataset_df,
    pd,
    prepare_tozai_distribution_frame,
    selected_spec,
):
    # セル概要: 分布比較に必要な summary dataframe を生成する。
    if dataset_df is None or dataset_df.empty:
        prepared_df = pd.DataFrame()
        distribution_summary_df = pd.DataFrame()
        pairwise_summary_df = pd.DataFrame()
        yearly_summary_df = pd.DataFrame()
    else:
        prepared_df = prepare_tozai_distribution_frame(
            dataset_df,
            metric_col=app_cfg.metric_col,
            group_col=selected_spec.group_col,
            date_col=selected_spec.date_col,
        )
        distribution_summary_df = build_tozai_distribution_summary(
            dataset_df,
            metric_col=app_cfg.metric_col,
            group_col=selected_spec.group_col,
            date_col=selected_spec.date_col,
        )
        pairwise_summary_df = build_tozai_pairwise_test_summary(
            dataset_df,
            metric_col=app_cfg.metric_col,
            group_col=selected_spec.group_col,
            date_col=selected_spec.date_col,
            max_test_samples=app_cfg.max_test_samples,
        )
        yearly_summary_df = build_tozai_yearly_summary(
            dataset_df,
            metric_col=app_cfg.metric_col,
            group_col=selected_spec.group_col,
            date_col=selected_spec.date_col,
        )
    return (
        distribution_summary_df,
        pairwise_summary_df,
        prepared_df,
        yearly_summary_df,
    )


@app.cell
def _(app_cfg, distribution_summary_df, mo, pairwise_summary_df):
    # セル概要: 分布統計と検定結果を表示する。
    summary_view = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## 4. Summary / Tests",
                        "",
                        f"- metric: `{app_cfg.metric_col}`",
                        "- `missing_rate` は生の staging 行ベースです。",
                        "- p-value は件数が非常に多いと過敏なので、`median_diff_b_minus_a` と `cohen_d_b_minus_a` も一緒に見ます。",
                    ]
                )
            ),
            mo.md("### Distribution Summary"),
            distribution_summary_df if not distribution_summary_df.empty else mo.md("No distribution summary."),
            mo.md("### Pairwise Tests"),
            pairwise_summary_df if not pairwise_summary_df.empty else mo.md("No pairwise test summary."),
        ]
    )
    summary_view
    return


@app.cell
def _(app_cfg, mo, np, plt, prepared_df):
    # セル概要: ヒストグラムと ECDF を描画する。
    if prepared_df.empty:
        distribution_plot_view = mo.md("## 5. Distribution Plots\n\nNo prepared data.")
    else:
        _labels = list(prepared_df["tozai_label"].dropna().unique())
        palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
        _fig, _axes = plt.subplots(1, 2, figsize=(12, 4.5))

        q01 = float(prepared_df["metric_value"].quantile(0.01))
        q99 = float(prepared_df["metric_value"].quantile(0.99))
        bins = np.linspace(q01, q99, 40) if q99 > q01 else 30

        for idx, _label in enumerate(_labels):
            values = prepared_df.loc[prepared_df["tozai_label"] == _label, "metric_value"].dropna().to_numpy()
            color = palette[idx % len(palette)]
            _axes[0].hist(
                values,
                bins=bins,
                density=True,
                histtype="step",
                linewidth=2,
                label=f"{_label} (n={len(values):,})",
                color=color,
            )
            sorted_values = np.sort(values)
            ecdf = np.arange(1, len(sorted_values) + 1) / len(sorted_values)
            _axes[1].plot(sorted_values, ecdf, label=_label, color=color, linewidth=2)

        _axes[0].set_title(f"{app_cfg.metric_col} density")
        _axes[0].set_xlabel(app_cfg.metric_col)
        _axes[0].set_ylabel("density")
        _axes[0].legend()

        _axes[1].set_title(f"{app_cfg.metric_col} ECDF")
        _axes[1].set_xlabel(app_cfg.metric_col)
        _axes[1].set_ylabel("cumulative share")
        _axes[1].legend()
        _fig.tight_layout()

        distribution_plot_view = mo.vstack(
            [
                mo.md("## 5. Distribution Plots"),
                mo.md("ヒストグラムは 1% - 99% quantile 範囲に絞って重ねています。"),
                _fig,
            ]
        )
    distribution_plot_view
    return


@app.cell
def _(app_cfg, mo, plt, prepared_df):
    # セル概要: 箱ひげ図で分布位置と散らばりを比較する。
    if prepared_df.empty:
        boxplot_view = mo.md("## 6. Box Plot\n\nNo prepared data.")
    else:
        _labels = list(prepared_df["tozai_label"].dropna().unique())
        data = [
            prepared_df.loc[prepared_df["tozai_label"] == _label, "metric_value"].dropna().to_numpy()
            for _label in _labels
        ]

        _fig, _ax = plt.subplots(figsize=(7, 4.5))
        _ax.boxplot(data, labels=_labels, showfliers=False)
        _ax.set_title(f"{app_cfg.metric_col} by tozai_cd")
        _ax.set_xlabel("group")
        _ax.set_ylabel(app_cfg.metric_col)
        _fig.tight_layout()
        boxplot_view = mo.vstack([mo.md("## 6. Box Plot"), _fig])
    boxplot_view
    return


@app.cell
def _(app_cfg, mo, plt, yearly_summary_df):
    # セル概要: 年ごとの中央値推移を描画する。
    if yearly_summary_df.empty:
        yearly_view = mo.md("## 7. Yearly Trend\n\nNo yearly summary.")
    else:
        _fig, _ax = plt.subplots(figsize=(9, 4.5))
        for _label, _group_df in yearly_summary_df.groupby("tozai_label", dropna=False):
            _ax.plot(
                _group_df["year"].astype(int),
                _group_df["median"],
                marker="o",
                linewidth=2,
                label=_label,
            )
            _ax.fill_between(
                _group_df["year"].astype(int),
                _group_df["p25"],
                _group_df["p75"],
                alpha=0.15,
            )

        _ax.set_title(f"Yearly median {app_cfg.metric_col}")
        _ax.set_xlabel("year")
        _ax.set_ylabel(app_cfg.metric_col)
        _ax.legend()
        _fig.tight_layout()
        yearly_view = mo.vstack(
            [
                mo.md("## 7. Yearly Trend"),
                mo.md("線は年次中央値、帯は IQR (`p25` - `p75`) です。"),
                _fig,
            ]
        )
    yearly_view
    return


@app.cell
def _(mo):
    # セル概要: notebook の読み方を補足する。
    mo.md(
        "\n".join(
            [
                "## 8. Reading Guide",
                "",
                "- `ECDF` が横にずれていれば、分布全体がずれている可能性があります。",
                "- `Yearly Trend` まで同方向なら、一時的な時期差ではなく構造差の可能性があります。",
                "- raw の `tozai_cd` はこの notebook ではコード値のまま扱っています。東西の意味づけは source 定義を確認してから行うのが安全です。",
            ]
        )
    )
    return


if __name__ == "__main__":
    app.run()
