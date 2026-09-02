import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebook 全体で使う依存を読み込む。
    import io
    import re
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import pandas as pd
    from pydantic import BaseModel, Field
    from sqlalchemy.exc import SQLAlchemyError

    return BaseModel, Field, Path, SQLAlchemyError, io, mo, pd, plt, re, sys


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
    from harp.core.modeling.workout_time_interactions import (
        DEFAULT_WORKOUT_INTERACTION_NAMES,
        DEFAULT_WORKOUT_INTERACTION_SPECS,
        build_heatmap_matrix,
        build_interaction_catalog,
        build_interaction_effect_summary,
        build_last1f_4f_heatmap_summary,
        build_late_sharpness_decile_summary,
        build_within_total4f_band_sharpness_summary,
        resolve_interaction_spec,
    )
    from harp.shared.db import read_sql_df
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    runtime_config = load_pipeline_runtime_config()

    return (
        DEFAULT_WORKOUT_INTERACTION_NAMES,
        DEFAULT_WORKOUT_INTERACTION_SPECS,
        build_heatmap_matrix,
        build_interaction_catalog,
        build_interaction_effect_summary,
        build_last1f_4f_heatmap_summary,
        build_late_sharpness_decile_summary,
        build_notebook_config,
        build_within_total4f_band_sharpness_summary,
        cache_dir,
        dataframe_cache_exists,
        load_dataframe_cache,
        project_root,
        read_sql_df,
        runtime_config,
        resolve_interaction_spec,
        save_dataframe_cache,
        validate_identifier,
    )


@app.cell
def _(mo):
    # セル概要: notebook の目的を表示する。
    mo.md(
        "\n".join(
            [
                "# Workout Late Sharpness Heatmap",
                "",
                "- `4F の割に終いが速い` を見るための exploratory notebook",
                "- `late_sharpness = (4F - 1F) / 3 - 1F` を使って、全体時計に対する終いの鋭さを測る",
                "- 4F bin × 1F bin のヒートマップと、late_sharpness の decile 比較を同時に確認する",
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
def _(BaseModel, DEFAULT_WORKOUT_INTERACTION_NAMES, Field, runtime_config):
    # セル概要: notebook の設定モデルと既定値を定義する。
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
        interaction_name: str = Field(default=DEFAULT_WORKOUT_INTERACTION_NAMES[0])
        n_bins: int = Field(default=6)

    cfg = AppConfig()
    return AppConfig, cfg


@app.cell
def _(DEFAULT_WORKOUT_INTERACTION_NAMES, cfg, mo):
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
    interaction_name_widget = mo.ui.dropdown(
        options=list(DEFAULT_WORKOUT_INTERACTION_NAMES),
        value=cfg.interaction_name,
        label="Interaction pair",
    )
    n_bins_widget = mo.ui.number(start=3, stop=10, step=1, value=cfg.n_bins, label="Heatmap bins")
    run_button = mo.ui.run_button(label="Load / Refresh")

    mo.vstack(
        [
            mo.md("## 1. Data Source / Pair"),
            db_url_widget,
            mart_table_widget,
            mo.hstack([train_year_start_widget, test_year_widget]),
            mo.hstack([start_date_widget, end_date_widget]),
            mo.hstack([race_level_min_widget, race_level_max_widget]),
            main_parquet_path_widget,
            mo.hstack([use_cache_widget, read_from_db_widget, refresh_db_widget, save_cache_widget]),
            mo.hstack([target_col_widget, interaction_name_widget, n_bins_widget]),
            mo.hstack([run_button]),
        ]
    )
    return (
        db_url_widget,
        end_date_widget,
        interaction_name_widget,
        main_parquet_path_widget,
        mart_table_widget,
        n_bins_widget,
        race_level_max_widget,
        race_level_min_widget,
        read_from_db_widget,
        refresh_db_widget,
        run_button,
        save_cache_widget,
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
    end_date_widget,
    interaction_name_widget,
    is_script_mode,
    main_parquet_path_widget,
    mart_table_widget,
    mo,
    n_bins_widget,
    race_level_max_widget,
    race_level_min_widget,
    read_from_db_widget,
    refresh_db_widget,
    save_cache_widget,
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
                "end_date": str(end_date_widget.value).strip(),
                "interaction_name": str(interaction_name_widget.value),
                "main_parquet_path": str(main_parquet_path_widget.value).strip(),
                "mart_table": str(mart_table_widget.value).strip(),
                "n_bins": int(n_bins_widget.value),
                "race_level_max": int(race_level_max_widget.value),
                "race_level_min": int(race_level_min_widget.value),
                "read_from_db": bool(read_from_db_widget.value),
                "refresh_db": bool(refresh_db_widget.value),
                "save_cache": bool(save_cache_widget.value),
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
def _(cache_dir, io, mo, plt, re):
    # セル概要: notebook 図を PNG 表示 + 保存しやすい形に整える helper を定義する。
    export_dir = cache_dir / "exports" / "workout_late_sharpness_heatmap"
    export_dir.mkdir(parents=True, exist_ok=True)

    def build_exportable_figure_view(
        figure,
        *,
        section_title: str,
        filename_stem: str,
        description: str | None = None,
        image_width: str = "100%",
    ):
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename_stem).strip("._") or "figure"
        output_path = export_dir / f"{safe_name}.png"
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=180, bbox_inches="tight")
        png_bytes = buffer.getvalue()
        output_path.write_bytes(png_bytes)
        plt.close(figure)

        items = [mo.md(section_title)]
        if description:
            items.append(mo.md(description))
        items.extend(
            [
                mo.image(
                    src=io.BytesIO(png_bytes),
                    alt=output_path.name,
                    width=image_width,
                    caption=f"PNG preview: {output_path.name}",
                ),
                mo.hstack(
                    [
                        mo.download(
                            data=png_bytes,
                            filename=output_path.name,
                            mimetype="image/png",
                            label="Download PNG",
                        ),
                        mo.md(
                            "\n".join(
                                [
                                    "画像を右クリックでコピー/保存できます。",
                                    f"保存先: `{output_path}`",
                                ]
                            )
                        ),
                    ],
                    align="center",
                    justify="start",
                ),
            ]
        )
        return mo.vstack(items)

    return (build_exportable_figure_view,)


@app.cell
def _(DEFAULT_WORKOUT_INTERACTION_SPECS, app_cfg, dataframe_cache_exists, load_dataframe_cache, pd, read_sql_df, resolve_cache_path, save_dataframe_cache, validate_identifier):
    # セル概要: cache or DB から分析用データフレームを取得する helper を定義する。
    base_columns = [
        "race_id",
        "held_date",
        "held_year",
        "surface",
        "distance_m",
        "race_level",
        "result_order",
        "is_place",
        "is_win",
    ]
    pair_columns = []
    for spec in DEFAULT_WORKOUT_INTERACTION_SPECS:
        pair_columns.append(spec.last1f_col)
        pair_columns.append(spec.total4f_col)

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
        query_columns = list(dict.fromkeys([*base_columns, *pair_columns]))
        col_text = ", ".join(validate_identifier(col, kind="column") for col in query_columns)
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
def _(app_cfg, build_interaction_catalog, build_interaction_effect_summary, dataset_df, pd, resolve_interaction_spec):
    # セル概要: 選択ペアの catalog と全体サマリを生成する。
    catalog_df = build_interaction_catalog()
    selected_spec = resolve_interaction_spec(app_cfg.interaction_name)
    if dataset_df is None or dataset_df.empty:
        effect_df = pd.DataFrame()
    else:
        effect_df = build_interaction_effect_summary(
            dataset_df,
            [app_cfg.interaction_name],
            target_col=app_cfg.target_col,
        )
    return catalog_df, effect_df, selected_spec


@app.cell
def _(app_cfg, catalog_df, effect_df, mo, selected_spec):
    # セル概要: 分析対象ペアの説明と全体効果を表示する。
    lines = [
        "## 3. Pair Definition",
        "",
        f"- pair: `{selected_spec.name}` / `{selected_spec.label}`",
        f"- 4F: `{selected_spec.total4f_col}`",
        f"- 1F: `{selected_spec.last1f_col}`",
        "- `late_sharpness = (4F - 1F) / 3 - 1F`",
        "- 値が大きいほど、全体時計に対して終いが鋭い方向です。",
    ]
    pair_view = mo.vstack(
        [
            mo.md("\n".join(lines)),
            mo.md("### Available Pairs"),
            catalog_df,
            mo.md("### Selected Pair Effect Summary"),
            effect_df if not effect_df.empty else mo.md("No effect summary."),
        ]
    )
    pair_view
    return


@app.cell
def _(app_cfg, build_heatmap_matrix, build_last1f_4f_heatmap_summary, build_late_sharpness_decile_summary, build_within_total4f_band_sharpness_summary, dataset_df, pd):
    # セル概要: 選択ペアの heatmap と late_sharpness 集計を生成する。
    if dataset_df is None or dataset_df.empty:
        heatmap_summary_df = pd.DataFrame()
        heatmap_matrix = pd.DataFrame()
        late_sharpness_df = pd.DataFrame()
        within_band_df = pd.DataFrame()
    else:
        heatmap_summary_df = build_last1f_4f_heatmap_summary(
            dataset_df,
            spec_name=app_cfg.interaction_name,
            target_col=app_cfg.target_col,
            n_bins=app_cfg.n_bins,
        )
        heatmap_matrix = build_heatmap_matrix(heatmap_summary_df, value_col="target_rate")
        late_sharpness_df = build_late_sharpness_decile_summary(
            dataset_df,
            spec_name=app_cfg.interaction_name,
            target_col=app_cfg.target_col,
            n_bins=app_cfg.n_bins,
        )
        within_band_df = build_within_total4f_band_sharpness_summary(
            dataset_df,
            spec_name=app_cfg.interaction_name,
            target_col=app_cfg.target_col,
            n_total4f_bins=app_cfg.n_bins,
            n_sharpness_bins=4,
        )
    return heatmap_matrix, heatmap_summary_df, late_sharpness_df, within_band_df


@app.cell
def _(app_cfg, build_exportable_figure_view, heatmap_matrix, heatmap_summary_df, mo, plt):
    # セル概要: 4F bin × 1F bin の target heatmap を描画する。
    if heatmap_matrix.empty:
        heatmap_view = mo.md("## 4. Heatmap\n\nNo heatmap summary.")
    else:
        _fig, _ax = plt.subplots(figsize=(max(7, len(heatmap_matrix.columns) * 0.9), max(5, len(heatmap_matrix.index) * 0.7)))
        _im = _ax.imshow(heatmap_matrix.values, aspect="auto", cmap="Blues", vmin=0.0, vmax=1.0)
        _ax.set_xticks(range(len(heatmap_matrix.columns)))
        _ax.set_xticklabels([f"{int(col):02d}" for col in heatmap_matrix.columns], rotation=45, ha="right")
        _ax.set_yticks(range(len(heatmap_matrix.index)))
        _ax.set_yticklabels([f"{int(idx):02d}" for idx in heatmap_matrix.index])
        _ax.set_xlabel("1F speed bin (1=fastest)")
        _ax.set_ylabel("4F speed bin (1=fastest)")
        _ax.set_title(f"{app_cfg.target_col} rate by 4F bin x 1F bin")
        _cbar = _fig.colorbar(_im, ax=_ax)
        _cbar.set_label(app_cfg.target_col)

        for y, total4f_bin in enumerate(heatmap_matrix.index):
            for x, last1f_bin in enumerate(heatmap_matrix.columns):
                value = heatmap_matrix.loc[total4f_bin, last1f_bin]
                match = heatmap_summary_df.loc[
                    (heatmap_summary_df["total4f_bin"] == total4f_bin)
                    & (heatmap_summary_df["last1f_bin"] == last1f_bin)
                ]
                n_obs = int(match["n_obs"].iloc[0]) if not match.empty else 0
                text_value = f"{value:.1%}\n(n={n_obs})"
                _ax.text(x, y, text_value, ha="center", va="center", fontsize=8, color="black")

        _fig.tight_layout()
        heatmap_view = build_exportable_figure_view(
            _fig,
            section_title="## 4. Heatmap",
            filename_stem=f"heatmap_{app_cfg.interaction_name}_{app_cfg.target_col}_bins{app_cfg.n_bins}",
            description="同じ 4F bin の中で右に行くほど 1F が速い群です。",
        )
    heatmap_view
    return


@app.cell
def _(app_cfg, build_exportable_figure_view, late_sharpness_df, mo, plt):
    # セル概要: late_sharpness の decile 別 target rate を描画する。
    if late_sharpness_df.empty:
        sharpness_plot_view = mo.md("## 5. Late Sharpness Deciles\n\nNo late_sharpness summary.")
    else:
        _fig, _axes = plt.subplots(1, 2, figsize=(11, 4))
        _axes[0].plot(
            late_sharpness_df["late_sharpness_bin"],
            late_sharpness_df["target_rate"],
            marker="o",
            color="#1f77b4",
        )
        _axes[0].fill_between(
            late_sharpness_df["late_sharpness_bin"],
            late_sharpness_df["target_rate_ci_low"],
            late_sharpness_df["target_rate_ci_high"],
            color="#1f77b4",
            alpha=0.2,
        )
        _axes[0].set_title(f"{app_cfg.target_col} by late_sharpness bin")
        _axes[0].set_xlabel("late_sharpness bin (1=sharpest)")
        _axes[0].set_ylabel(app_cfg.target_col)
        _axes[0].set_ylim(0.0, 1.0)

        _axes[1].plot(
            late_sharpness_df["late_sharpness_bin"],
            late_sharpness_df["mean_late_sharpness"],
            marker="o",
            color="#d62728",
        )
        _axes[1].set_title("mean late_sharpness by bin")
        _axes[1].set_xlabel("late_sharpness bin (1=sharpest)")
        _axes[1].set_ylabel("mean late_sharpness")
        _fig.tight_layout()
        sharpness_plot_view = build_exportable_figure_view(
            _fig,
            section_title="## 5. Late Sharpness Deciles",
            filename_stem=f"late_sharpness_deciles_{app_cfg.interaction_name}_{app_cfg.target_col}_bins{app_cfg.n_bins}",
        )
    sharpness_plot_view
    return


@app.cell
def _(heatmap_summary_df, late_sharpness_df, mo, within_band_df):
    # セル概要: 集計テーブルを表示する。
    tables_view = mo.vstack(
        [
            mo.md("## 6. Summary Tables"),
            mo.md("### Heatmap Summary"),
            heatmap_summary_df if not heatmap_summary_df.empty else mo.md("No heatmap summary."),
            mo.md("### Late Sharpness Deciles"),
            late_sharpness_df if not late_sharpness_df.empty else mo.md("No late_sharpness summary."),
            mo.md("### Within Same 4F Band: sharpest vs dullest finish"),
            within_band_df if not within_band_df.empty else mo.md("No within-band summary."),
        ]
    )
    tables_view
    return


if __name__ == "__main__":
    app.run()
