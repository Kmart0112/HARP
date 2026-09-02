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
    import pandas as pd
    from pydantic import BaseModel, Field
    from sqlalchemy.exc import SQLAlchemyError

    return BaseModel, Field, Path, SQLAlchemyError, mo, pd, plt, sys


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
    from harp.core.modeling.workout_time_relationships import (
        DEFAULT_WORKOUT_TIME_FEATURES,
        build_availability_summary,
        build_decile_summary,
        build_effect_summary,
        build_fast_slow_segment_summary,
        build_feature_catalog,
    )
    from harp.shared.db import read_sql_df
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    runtime_config = load_pipeline_runtime_config()

    return (
        DEFAULT_WORKOUT_TIME_FEATURES,
        build_availability_summary,
        build_decile_summary,
        build_effect_summary,
        build_fast_slow_segment_summary,
        build_feature_catalog,
        build_notebook_config,
        cache_dir,
        dataframe_cache_exists,
        load_dataframe_cache,
        project_root,
        read_sql_df,
        runtime_config,
        save_dataframe_cache,
        validate_identifier,
    )


@app.cell
def _(mo):
    # セル概要: notebook の目的を表示する。
    mo.md(
        "\n".join(
            [
                "# Workout Time Relationships Overview",
                "",
                "- 調教時計とレース結果の関係だけを先に確認する exploratory notebook",
                "- `m_train_race_horse_past5` / analysis cache を入力にして、欠損率・単変量傾向・軽調整の関係を整理する",
                "- 生の秒比較は `wood` / `hanro` / `current` / `week1` を分けて解釈する前提",
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
def _(BaseModel, DEFAULT_WORKOUT_TIME_FEATURES, Field, runtime_config):
    # セル概要: notebook の設定モデルと既定値を定義する。
    default_feature = DEFAULT_WORKOUT_TIME_FEATURES[0]

    class AppConfig(BaseModel):
        db_url: str = Field(default=runtime_config.database.db_url)
        mart_table: str = Field(default=runtime_config.mart.training_mart_table)
        train_year_start: int = Field(default=2018)
        test_year: int = Field(default=2025)
        start_date: str = Field(default="2018-01-01")
        end_date: str = Field(default="2025-12-31")
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        main_parquet_path: str = Field(default="")
        use_cache: bool = Field(default=True)
        read_from_db: bool = Field(default=True)
        refresh_db: bool = Field(default=False)
        save_cache: bool = Field(default=False)
        target_col: str = Field(default="is_place")
        detail_feature: str = Field(default=default_feature)
        segment_col: str = Field(default="surface")

    cfg = AppConfig()
    return AppConfig, cfg


@app.cell
def _(DEFAULT_WORKOUT_TIME_FEATURES, cfg, mo):
    # セル概要: データソースと集計条件の UI を表示する。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    mart_table_widget = mo.ui.text(label="Mart table", value=cfg.mart_table, full_width=True)
    train_year_start_widget = mo.ui.number(start=2010, stop=2030, step=1, value=cfg.train_year_start, label="Train year start")
    test_year_widget = mo.ui.number(start=2015, stop=2030, step=1, value=cfg.test_year, label="Test year")
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)
    end_date_widget = mo.ui.text(label="End date", value=cfg.end_date)
    race_level_min_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_min, label="Race level min")
    race_level_max_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_max, label="Race level max")
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
    target_col_widget = mo.ui.dropdown(options=["is_place", "is_win"], value=cfg.target_col, label="Target")
    detail_feature_widget = mo.ui.dropdown(
        options=list(DEFAULT_WORKOUT_TIME_FEATURES),
        value=cfg.detail_feature,
        label="Detail feature",
    )
    segment_col_widget = mo.ui.dropdown(
        options=["surface", "race_level", "held_year"],
        value=cfg.segment_col,
        label="Segment",
    )
    run_button = mo.ui.run_button(label="Load / Refresh")

    mo.vstack(
        [
            mo.md("## 1. Data Source / Filters"),
            db_url_widget,
            mart_table_widget,
            mo.hstack([train_year_start_widget, test_year_widget]),
            mo.hstack([start_date_widget, end_date_widget]),
            mo.hstack([race_level_min_widget, race_level_max_widget]),
            main_parquet_path_widget,
            mo.hstack([use_cache_widget, read_from_db_widget, refresh_db_widget, save_cache_widget]),
            mo.hstack([target_col_widget, detail_feature_widget, segment_col_widget]),
            mo.hstack([run_button]),
        ]
    )
    return (
        db_url_widget,
        detail_feature_widget,
        end_date_widget,
        main_parquet_path_widget,
        mart_table_widget,
        race_level_max_widget,
        race_level_min_widget,
        read_from_db_widget,
        refresh_db_widget,
        run_button,
        save_cache_widget,
        segment_col_widget,
        start_date_widget,
        target_col_widget,
        test_year_widget,
        train_year_start_widget,
        use_cache_widget,
    )


@app.cell
def _(
    AppConfig,
    build_notebook_config,
    cfg,
    db_url_widget,
    detail_feature_widget,
    end_date_widget,
    is_script_mode,
    main_parquet_path_widget,
    mart_table_widget,
    mo,
    race_level_max_widget,
    race_level_min_widget,
    read_from_db_widget,
    refresh_db_widget,
    save_cache_widget,
    segment_col_widget,
    start_date_widget,
    target_col_widget,
    test_year_widget,
    train_year_start_widget,
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
                "detail_feature": str(detail_feature_widget.value),
                "end_date": str(end_date_widget.value).strip(),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "mart_table": str(mart_table_widget.value).strip(),
                "race_level_max": int(race_level_max_widget.value),
                "race_level_min": int(race_level_min_widget.value),
                "read_from_db": bool(read_from_db_widget.value),
                "refresh_db": bool(refresh_db_widget.value),
                "save_cache": bool(save_cache_widget.value),
                "segment_col": str(segment_col_widget.value),
                "start_date": str(start_date_widget.value).strip(),
                "target_col": str(target_col_widget.value),
                "test_year": int(test_year_widget.value),
                "train_year_start": int(train_year_start_widget.value),
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
        return cache_dir / f"m_train_race_horse_past5_{app_cfg.train_year_start}_{app_cfg.test_year}.parquet"

    return (resolve_cache_path,)


@app.cell
def _(DEFAULT_WORKOUT_TIME_FEATURES, app_cfg, dataframe_cache_exists, load_dataframe_cache, pd, read_sql_df, resolve_cache_path, save_dataframe_cache, validate_identifier):
    # セル概要: cache or DB から分析用データフレームを取得する helper を定義する。
    base_columns = [
        "race_id",
        "held_date",
        "held_year",
        "surface",
        "distance_m",
        "race_level",
        "num_starters",
        "result_order",
        "is_place",
        "is_win",
    ]

    def _filter_frame(df_source: pd.DataFrame) -> pd.DataFrame:
        work = df_source.copy()
        if "held_date" in work.columns:
            work["held_date"] = pd.to_datetime(work["held_date"], errors="coerce")
            if str(app_cfg.start_date).strip():
                work = work.loc[work["held_date"] >= pd.Timestamp(app_cfg.start_date)]
            if str(app_cfg.end_date).strip():
                work = work.loc[work["held_date"] <= pd.Timestamp(app_cfg.end_date)]
        if "race_level" in work.columns:
            work = work.loc[
                work["race_level"].between(app_cfg.race_level_min, app_cfg.race_level_max, inclusive="both")
            ]
        return work.reset_index(drop=True)

    def load_source_dataframe() -> tuple[pd.DataFrame, str]:
        cache_path = resolve_cache_path(app_cfg)
        if app_cfg.use_cache and dataframe_cache_exists(cache_path) and not app_cfg.refresh_db:
            return _filter_frame(load_dataframe_cache(cache_path)), f"cache: {cache_path}"

        if not app_cfg.read_from_db:
            raise FileNotFoundError(f"DataFrame cache not found and DB read disabled: {cache_path}")

        table_name = validate_identifier(app_cfg.mart_table, kind="table")
        query_columns = [*base_columns, *DEFAULT_WORKOUT_TIME_FEATURES]
        unique_columns = list(dict.fromkeys(query_columns))
        col_text = ", ".join(validate_identifier(col, kind="column") for col in unique_columns)
        sql = f"""
        SELECT {col_text}
        FROM {table_name}
        WHERE held_date >= :start_date
          AND held_date <= :end_date
          AND race_level BETWEEN :race_level_min AND :race_level_max
        ORDER BY held_date DESC, race_id DESC
        """
        df_source = read_sql_df(
            sql,
            params={
                "start_date": app_cfg.start_date,
                "end_date": app_cfg.end_date,
                "race_level_min": app_cfg.race_level_min,
                "race_level_max": app_cfg.race_level_max,
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
        dataset_status_view = mo.md(f"## 2. Dataset Status\n\n`{dataset_error}`")
    elif dataset_df is None:
        dataset_status_view = mo.md("## 2. Dataset Status\n\n`Load / Refresh` を押すと集計します。")
    else:
        dataset_status_view = mo.md(
            "\n".join(
                [
                    "## 2. Dataset Status",
                    "",
                    f"- source: `{dataset_source}`",
                    f"- rows: `{len(dataset_df):,}`",
                ]
            )
        )
    dataset_status_view
    return dataset_df, dataset_error, dataset_source


@app.cell
def _(build_availability_summary, build_effect_summary, build_feature_catalog, dataset_df, pd):
    # セル概要: 全体集計テーブルを生成する。
    if dataset_df is None or dataset_df.empty:
        catalog_df = build_feature_catalog()
        availability_df = pd.DataFrame()
        effect_df = pd.DataFrame()
    else:
        catalog_df = build_feature_catalog()
        availability_df = build_availability_summary(dataset_df)
        effect_df = build_effect_summary(dataset_df)
    return availability_df, catalog_df, effect_df


@app.cell
def _(availability_df, catalog_df, effect_df, mo):
    # セル概要: feature catalog と全体サマリを表示する。
    if catalog_df.empty:
        overview_view = mo.md("## 3. Feature Catalog / Overall Summary\n\nNo catalog.")
    else:
        overview_view = mo.vstack(
            [
                mo.md("## 3. Feature Catalog"),
                catalog_df,
                mo.md("## 4. Availability Summary"),
                availability_df if not availability_df.empty else mo.md("No availability summary."),
                mo.md("## 5. Effect Summary"),
                effect_df if not effect_df.empty else mo.md("No effect summary."),
            ]
        )
    overview_view
    return


@app.cell
def _(app_cfg, build_decile_summary, build_fast_slow_segment_summary, dataset_df, pd):
    # セル概要: 選択 feature の詳細テーブルを生成する。
    if dataset_df is None or dataset_df.empty:
        decile_df = pd.DataFrame()
        segment_df = pd.DataFrame()
    else:
        decile_df = build_decile_summary(dataset_df, app_cfg.detail_feature, target_col=app_cfg.target_col)
        segment_df = build_fast_slow_segment_summary(
            dataset_df,
            app_cfg.detail_feature,
            target_col=app_cfg.target_col,
            segment_col=app_cfg.segment_col,
        )
    return decile_df, segment_df


@app.cell
def _(app_cfg, dataset_df, decile_df, mo, pd, segment_df):
    # セル概要: 選択 feature の解釈補助テキストを作る。
    if dataset_df is None or dataset_df.empty:
        detail_text = mo.md("## 6. Detail View\n\nNo data loaded.")
    else:
        non_null = int(pd.to_numeric(dataset_df[app_cfg.detail_feature], errors="coerce").notna().sum())
        detail_text = mo.md(
            "\n".join(
                [
                    "## 6. Detail View",
                    "",
                    f"- feature: `{app_cfg.detail_feature}`",
                    f"- target: `{app_cfg.target_col}`",
                    f"- segment: `{app_cfg.segment_col}`",
                    f"- non-null rows: `{non_null:,}`",
                    "- `speed_decile=1` が最も速い群です。",
                    "- logistic の係数は `1sd 速くなる` 方向で定義しているので、正なら好走方向です。",
                ]
            )
        )
    detail_text
    return


@app.cell
def _(app_cfg, decile_df, mo, plt):
    # セル概要: 選択 feature の十分位プロットを描く。
    if decile_df.empty:
        decile_plot_view = mo.md("### Decile Plot\n\nNo decile summary.")
    else:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))

        axes[0].plot(decile_df["speed_decile"], decile_df["target_rate"], marker="o", color="#1f77b4")
        axes[0].fill_between(
            decile_df["speed_decile"],
            decile_df["target_rate_ci_low"],
            decile_df["target_rate_ci_high"],
            color="#1f77b4",
            alpha=0.2,
        )
        axes[0].set_title(f"{app_cfg.target_col} by speed decile")
        axes[0].set_xlabel("speed decile (1=fastest)")
        axes[0].set_ylabel(app_cfg.target_col)
        axes[0].set_ylim(0.0, 1.0)

        axes[1].plot(decile_df["speed_decile"], decile_df["mean_result_order"], marker="o", color="#d62728")
        axes[1].set_title("mean result_order by speed decile")
        axes[1].set_xlabel("speed decile (1=fastest)")
        axes[1].set_ylabel("mean result_order")
        axes[1].invert_yaxis()

        fig.tight_layout()
        decile_plot_view = mo.vstack([mo.md("### Decile Plot"), fig])
    decile_plot_view
    return


@app.cell
def _(decile_df, mo, segment_df):
    # セル概要: 選択 feature の詳細テーブルを表示する。
    detail_table_view = mo.vstack(
        [
            mo.md("### Decile Summary"),
            decile_df if not decile_df.empty else mo.md("No decile summary."),
            mo.md("### Fast vs Slow by Segment"),
            segment_df if not segment_df.empty else mo.md("No segment summary."),
        ]
    )
    detail_table_view
    return


if __name__ == "__main__":
    app.run()
