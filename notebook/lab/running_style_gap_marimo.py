import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebook で利用する依存を読み込む。
    import hashlib
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from pydantic import BaseModel, Field
    from sqlalchemy import create_engine, text

    return (
        BaseModel,
        Field,
        Path,
        create_engine,
        hashlib,
        mo,
        np,
        pd,
        plt,
        sys,
        text,
    )


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトルートと共通 helper を解決する。
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
    from harp.controllers import build_notebook_config
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    runtime_config = load_pipeline_runtime_config()
    return (
        build_notebook_config,
        cache_dir,
        dataframe_cache_exists,
        load_dataframe_cache,
        project_root,
        resolve_dataframe_cache_path,
        runtime_config,
        save_dataframe_cache,
    )


@app.cell
def _(mo):
    # セル概要: notebook のタイトルと使い方を表示する。
    mo.md(
        "\n".join(
            [
                "# Running Style Gap Viewer",
                "",
                "- `running_style_avg3` と実測脚質、`horse_corner4_avg3` / `corner4_rate_z` と実測 pos4 を確認する exploratory notebook",
                "- 主に `ヒートマップ / 丸め混同行列 / 2D分布 / delta 分布 / 条件別集計` を見る",
                "- 対象は `lab.m_running_style_gap`",
            ]
        )
    )
    return


@app.cell
def _(mo):
    # セル概要: script 実行か interactive 実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, runtime_config):
    # セル概要: notebook 全体の既定設定を定義する。
    class AppConfig(BaseModel):
        db_url: str = Field(default=runtime_config.database.db_url)
        table: str = Field(default="lab.m_running_style_gap")
        start_date: str = Field(default="2023-01-01")
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        row_limit: int = Field(default=300_000)
        use_cache_default: bool = Field(default=True)
        refresh_db_default: bool = Field(default=False)
        min_num_past3_races: int = Field(default=3)
        surface_filter: str = Field(default="all")
        split_by: str = Field(default="surface")
        heatmap_mode: str = Field(default="row_share")

    cfg = AppConfig()
    return AppConfig, cfg


@app.cell
def _(cfg, mo):
    # セル概要: データ取得と表示条件の UI を構築する。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    table_widget = mo.ui.text(label="Table", value=cfg.table, full_width=True)
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)
    race_level_min_widget = mo.ui.number(
        start=1, stop=10, step=1, value=cfg.race_level_min, label="Race level min"
    )
    race_level_max_widget = mo.ui.number(
        start=1, stop=10, step=1, value=cfg.race_level_max, label="Race level max"
    )
    row_limit_widget = mo.ui.number(
        start=10_000, stop=2_000_000, step=10_000, value=cfg.row_limit, label="Row limit"
    )
    use_cache_widget = mo.ui.switch(value=cfg.use_cache_default, label="Use cache")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_db_default, label="Force refresh DB")
    min_num_past3_widget = mo.ui.number(
        start=1, stop=3, step=1, value=cfg.min_num_past3_races, label="Min num_past3_races"
    )
    surface_filter_widget = mo.ui.dropdown(
        options={"all": "all", "turf": "0", "dirt": "1"},
        value=cfg.surface_filter,
        label="Surface filter",
    )
    split_by_widget = mo.ui.dropdown(
        options=["surface", "distance_bucket", "race_level"],
        value=cfg.split_by,
        label="Split by",
    )
    heatmap_mode_widget = mo.ui.dropdown(
        options=["row_share", "count"],
        value=cfg.heatmap_mode,
        label="Heatmap mode",
    )
    run_button = mo.ui.run_button(label="Load / Refresh")

    mo.vstack(
        [
            mo.md("## 1. Query / Filter"),
            db_url_widget,
            table_widget,
            mo.hstack([start_date_widget, race_level_min_widget, race_level_max_widget]),
            mo.hstack([row_limit_widget, min_num_past3_widget]),
            mo.hstack([surface_filter_widget, split_by_widget, heatmap_mode_widget]),
            mo.hstack([use_cache_widget, refresh_db_widget, run_button]),
        ]
    )
    return (
        db_url_widget,
        heatmap_mode_widget,
        min_num_past3_widget,
        race_level_max_widget,
        race_level_min_widget,
        refresh_db_widget,
        row_limit_widget,
        run_button,
        split_by_widget,
        start_date_widget,
        surface_filter_widget,
        table_widget,
        use_cache_widget,
    )


@app.cell
def _(
    AppConfig,
    build_notebook_config,
    cfg,
    db_url_widget,
    heatmap_mode_widget,
    is_script_mode,
    min_num_past3_widget,
    mo,
    race_level_max_widget,
    race_level_min_widget,
    refresh_db_widget,
    row_limit_widget,
    split_by_widget,
    start_date_widget,
    surface_filter_widget,
    table_widget,
    use_cache_widget,
):
    # セル概要: script / interactive の入力値を同一設定へ正規化する。
    if is_script_mode:
        app_cfg = build_notebook_config(AppConfig, defaults=cfg, cli_args=mo.cli_args())
    else:
        app_cfg = build_notebook_config(
            AppConfig,
            defaults=cfg,
            overrides={
                "db_url": str(db_url_widget.value).strip(),
                "heatmap_mode": str(heatmap_mode_widget.value),
                "min_num_past3_races": int(min_num_past3_widget.value),
                "race_level_max": int(race_level_max_widget.value),
                "race_level_min": int(race_level_min_widget.value),
                "refresh_db_default": bool(refresh_db_widget.value),
                "row_limit": int(row_limit_widget.value),
                "split_by": str(split_by_widget.value),
                "start_date": str(start_date_widget.value).strip(),
                "surface_filter": str(surface_filter_widget.value),
                "table": str(table_widget.value).strip(),
                "use_cache_default": bool(use_cache_widget.value),
            },
        )
    return (app_cfg,)


@app.cell
def _(hashlib, pd):
    # セル概要: 集計で使う補助関数を定義する。
    style_label_map = {
        1: "1",
        2: "2",
        3: "3",
        4: "4",
    }
    surface_label_map = {
        0: "turf",
        1: "dirt",
    }

    def make_cache_path(cache_dir, app_cfg):
        key = "|".join(
            [
                app_cfg.table,
                app_cfg.start_date,
                str(app_cfg.race_level_min),
                str(app_cfg.race_level_max),
                str(app_cfg.row_limit),
            ]
        )
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
        return cache_dir / f"running_style_gap_{digest}.parquet"

    def to_distance_bucket(distance_m: pd.Series) -> pd.Series:
        return pd.cut(
            distance_m,
            bins=[0, 1400, 1800, 2200, 5000],
            labels=["sprint", "mile", "middle", "long"],
            right=True,
        ).astype("object")

    def build_error_metrics_df(targets: list[tuple[str, pd.Series, pd.Series]]) -> pd.DataFrame:
        _rows: list[dict[str, float | int | str]] = []
        for _name, _actual, _pred in targets:
            _frame = pd.DataFrame({"actual": _actual, "pred": _pred}).dropna()
            if _frame.empty:
                _rows.append(
                    {
                        "target": _name,
                        "rows": 0,
                        "mse": float("nan"),
                        "rmse": float("nan"),
                        "mae": float("nan"),
                        "bias": float("nan"),
                    }
                )
                continue
            _err = _frame["actual"] - _frame["pred"]
            _mse = (_err ** 2).mean()
            _rows.append(
                {
                    "target": _name,
                    "rows": int(len(_frame)),
                    "mse": float(_mse),
                    "rmse": float(_mse ** 0.5),
                    "mae": float(_err.abs().mean()),
                    "bias": float(_err.mean()),
                }
            )
        return pd.DataFrame(_rows)

    return (
        build_error_metrics_df,
        make_cache_path,
        style_label_map,
        surface_label_map,
        to_distance_bucket,
    )


@app.cell
def _(is_script_mode, run_button):
    # セル概要: script mode では自動実行し、interactive ではボタン押下で実行する。
    should_run = is_script_mode or bool(run_button.value)
    return (should_run,)


@app.cell
def _(
    app_cfg,
    cache_dir,
    create_engine,
    dataframe_cache_exists,
    load_dataframe_cache,
    make_cache_path,
    pd,
    resolve_dataframe_cache_path,
    save_dataframe_cache,
    should_run,
    text,
):
    # セル概要: DB または cache から対象データを読み込む。
    if not should_run:
        raise ValueError("Press `Load / Refresh` to start.")

    if not app_cfg.db_url:
        raise ValueError("HARP_DB_URL is empty.")

    cache_path = make_cache_path(cache_dir, app_cfg)
    use_cache = app_cfg.use_cache_default and dataframe_cache_exists(cache_path) and (not app_cfg.refresh_db_default)

    if use_cache:
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading: {cache_source_path}")
        raw_df = load_dataframe_cache(cache_path)
    else:
        engine = create_engine(app_cfg.db_url)
        sql = text(
            f"""
            SELECT
              held_date,
              race_id,
              kettonum,
              jyo_cd,
              distance_m,
              surface,
              race_level,
              result_order,
              is_place,
              actual_running_style_cd,
              actual_rank_4c,
              actual_corner4_pos,
              running_style_avg3,
              avg3_running_style_rounded,
              horse_corner4_avg3,
              corner4_rate_z,
              actual_corner4_z,
              num_past3_races,
              running_style_delta,
              running_style_abs_delta,
              avg3_rounded_match_flag,
              corner4_avg_delta,
              corner4_avg_abs_delta,
              corner4_z_delta,
              corner4_z_abs_delta
            FROM {app_cfg.table}
            WHERE held_date >= :start_date
              AND race_level BETWEEN :race_level_min AND :race_level_max
              AND actual_running_style_cd IS NOT NULL
              AND running_style_avg3 IS NOT NULL
            ORDER BY held_date, race_id
            LIMIT :row_limit
            """
        )
        with engine.connect().execution_options(stream_results=True) as conn:
            raw_df = pd.read_sql_query(
                sql,
                conn,
                params={
                    "start_date": app_cfg.start_date,
                    "race_level_min": app_cfg.race_level_min,
                    "race_level_max": app_cfg.race_level_max,
                    "row_limit": app_cfg.row_limit,
                },
            )
        if app_cfg.use_cache_default:
            save_dataframe_cache(raw_df, cache_path)
            print(f"[cache] saved: {cache_path}")

    if raw_df.empty:
        raise ValueError("Query returned 0 rows.")
    return (raw_df,)


@app.cell
def _(
    app_cfg,
    np,
    pd,
    raw_df,
    style_label_map,
    surface_label_map,
    to_distance_bucket,
):
    # セル概要: 可視化に必要な派生列を作り、UI 条件でフィルタする。
    df = raw_df.copy()
    df["held_date"] = pd.to_datetime(df["held_date"])
    df["surface_name"] = df["surface"].map(surface_label_map).fillna(df["surface"].astype(str))
    df["distance_bucket"] = to_distance_bucket(df["distance_m"]).fillna("unknown")
    df["actual_running_style_cd"] = df["actual_running_style_cd"].astype(int)
    df["actual_rank_4c"] = df["actual_rank_4c"].astype(float)
    df["actual_corner4_pos"] = df["actual_corner4_pos"].astype(float)
    df["running_style_avg3"] = df["running_style_avg3"].astype(float)
    df["horse_corner4_avg3"] = df["horse_corner4_avg3"].astype(float)
    df["corner4_rate_z"] = df["corner4_rate_z"].astype(float)
    df["actual_corner4_z"] = df["actual_corner4_z"].astype(float)
    df["rounded_style"] = df["avg3_running_style_rounded"].fillna(
        np.rint(df["running_style_avg3"]).clip(1, 4)
    ).astype(int)
    df["delta"] = df["running_style_delta"].fillna(
        df["actual_running_style_cd"] - df["running_style_avg3"]
    )
    df["abs_delta"] = df["running_style_abs_delta"].fillna(df["delta"].abs())
    df["avg3_bucket"] = df["running_style_avg3"].round(2)
    df["actual_style_label"] = df["actual_running_style_cd"].map(style_label_map).fillna(
        df["actual_running_style_cd"].astype(str)
    )
    df["rounded_style_label"] = df["rounded_style"].map(style_label_map).fillna(df["rounded_style"].astype(str))
    df["round_match"] = df["avg3_rounded_match_flag"].fillna(
        (df["rounded_style"] == df["actual_running_style_cd"]).astype(int)
    ).astype(int)
    df["same_or_adjacent"] = (
        np.abs(df["rounded_style"] - df["actual_running_style_cd"]) <= 1
    ).astype(int)
    df["corner4_avg_delta"] = df["corner4_avg_delta"].fillna(
        df["actual_corner4_pos"] - df["horse_corner4_avg3"]
    )
    df["corner4_avg_abs_delta"] = df["corner4_avg_abs_delta"].fillna(df["corner4_avg_delta"].abs())
    df["corner4_z_delta"] = df["corner4_z_delta"].fillna(
        df["actual_corner4_z"] - df["corner4_rate_z"]
    )
    df["corner4_z_abs_delta"] = df["corner4_z_abs_delta"].fillna(df["corner4_z_delta"].abs())

    filtered_df = df[df["num_past3_races"] >= int(app_cfg.min_num_past3_races)].copy()
    if app_cfg.surface_filter != "all":
        filtered_df = filtered_df[filtered_df["surface"].astype(str) == str(app_cfg.surface_filter)].copy()

    if filtered_df.empty:
        raise ValueError("Filtered dataset is empty. Relax filters and rerun.")
    return (filtered_df,)


@app.cell
def _(build_error_metrics_df, filtered_df):
    # セル概要: 各比較対象の MSE 系指標を集計する。
    metrics_df = build_error_metrics_df(
        [
            ("running_style_avg3", filtered_df["actual_running_style_cd"], filtered_df["running_style_avg3"]),
            ("running_style_rounded", filtered_df["actual_running_style_cd"], filtered_df["rounded_style"]),
            ("corner4_avg3", filtered_df["actual_corner4_pos"], filtered_df["horse_corner4_avg3"]),
            ("corner4_rate_z", filtered_df["actual_corner4_z"], filtered_df["corner4_rate_z"]),
        ]
    )
    return (metrics_df,)


@app.cell
def _(app_cfg, filtered_df, metrics_df, mo):
    # セル概要: フィルタ後データの件数と主要指標を表示する。
    summary_lines = [
        "## 2. Summary",
        "",
        f"- rows: `{len(filtered_df):,}`",
        f"- mean abs delta: `{filtered_df['abs_delta'].mean():.3f}`",
        f"- median abs delta: `{filtered_df['abs_delta'].median():.3f}`",
        f"- rounded match rate: `{filtered_df['round_match'].mean():.1%}`",
        f"- same or adjacent after rounding: `{filtered_df['same_or_adjacent'].mean():.1%}`",
        f"- pos4 avg mean abs delta: `{filtered_df['corner4_avg_abs_delta'].dropna().mean():.3f}`",
        f"- pos4 z mean abs delta: `{filtered_df['corner4_z_abs_delta'].dropna().mean():.3f}`",
        f"- split by: `{app_cfg.split_by}`",
        f"- heatmap mode: `{app_cfg.heatmap_mode}`",
        "",
        "`running_style` の MSE は順序カテゴリを連続値として見た参考値です。",
    ]
    mo.vstack([mo.md("\n".join(summary_lines)), metrics_df, filtered_df.head(8)])
    return


@app.cell
def _(app_cfg, filtered_df, plt):
    # セル概要: 平均脚質と実測脚質の対応をヒートマップで可視化する。
    heatmap_df = (
        filtered_df.groupby(["actual_style_label", "avg3_bucket"], observed=True)
        .size()
        .rename("rows")
        .reset_index()
    )
    heatmap_matrix = heatmap_df.pivot(
        index="actual_style_label",
        columns="avg3_bucket",
        values="rows",
    ).fillna(0.0)
    heatmap_matrix = heatmap_matrix.sort_index(axis=0).sort_index(axis=1)

    if app_cfg.heatmap_mode == "row_share":
        plot_matrix = heatmap_matrix.div(heatmap_matrix.sum(axis=1).replace(0, 1), axis=0)
        colorbar_label = "row share"
        fmt = ".0%"
    else:
        plot_matrix = heatmap_matrix
        colorbar_label = "count"
        fmt = ".0f"

    _fig, _ax = plt.subplots(figsize=(max(8, len(plot_matrix.columns) * 0.7), 3.8))
    _im = _ax.imshow(plot_matrix.values, aspect="auto", cmap="Blues")
    _ax.set_xticks(range(len(plot_matrix.columns)))
    _ax.set_xticklabels([f"{_col:.2f}" for _col in plot_matrix.columns], rotation=45, ha="right")
    _ax.set_yticks(range(len(plot_matrix.index)))
    _ax.set_yticklabels(plot_matrix.index)
    _ax.set_xlabel("running_style_avg3")
    _ax.set_ylabel("actual running_style")
    _ax.set_title("Actual running_style vs running_style_avg3")
    _cbar = _fig.colorbar(_im, ax=_ax)
    _cbar.set_label(colorbar_label)

    for _y, _row_name in enumerate(plot_matrix.index):
        for _x, _col_name in enumerate(plot_matrix.columns):
            _value = plot_matrix.loc[_row_name, _col_name]
            _text_value = format(_value, fmt)
            _ax.text(_x, _y, _text_value, ha="center", va="center", fontsize=8, color="black")

    _fig.tight_layout()
    _fig
    return


@app.cell
def _(filtered_df, plt):
    # セル概要: 丸め後脚質と実測脚質の混同行列を描画する。
    confusion = (
        filtered_df.groupby(["actual_style_label", "rounded_style_label"], observed=True)
        .size()
        .rename("rows")
        .reset_index()
        .pivot(index="actual_style_label", columns="rounded_style_label", values="rows")
        .fillna(0.0)
    )
    confusion = confusion.sort_index(axis=0).sort_index(axis=1)
    confusion_share = confusion.div(confusion.sum(axis=1).replace(0, 1), axis=0)

    _fig = plt.figure(figsize=(5.2, 4.0))
    _ax = _fig.add_subplot(111)
    _im = _ax.imshow(confusion_share.values, aspect="auto", cmap="Greens", vmin=0.0, vmax=1.0)
    _ax.set_xticks(range(len(confusion_share.columns)))
    _ax.set_xticklabels(confusion_share.columns)
    _ax.set_yticks(range(len(confusion_share.index)))
    _ax.set_yticklabels(confusion_share.index)
    _ax.set_xlabel("rounded running_style_avg3")
    _ax.set_ylabel("actual running_style")
    _ax.set_title("Rounded confusion matrix")
    _cbar = _fig.colorbar(_im, ax=_ax)
    _cbar.set_label("row share")

    for _y, _row_name in enumerate(confusion_share.index):
        for _x, _col_name in enumerate(confusion_share.columns):
            _value = confusion_share.loc[_row_name, _col_name]
            _ax.text(_x, _y, f"{_value:.0%}", ha="center", va="center", fontsize=9, color="black")

    _fig.tight_layout()
    _fig
    return


@app.cell
def _(filtered_df, plt):
    # セル概要: signed delta と absolute delta の分布を描画する。
    _fig, _axes = plt.subplots(1, 2, figsize=(11, 3.8))

    _axes[0].hist(filtered_df["delta"], bins=24, color="#4C72B0", edgecolor="white")
    _axes[0].axvline(0.0, color="black", linewidth=1)
    _axes[0].set_title("Signed delta")
    _axes[0].set_xlabel("running_style - running_style_avg3")
    _axes[0].set_ylabel("rows")

    _axes[1].hist(filtered_df["abs_delta"], bins=20, color="#55A868", edgecolor="white")
    _axes[1].set_title("Absolute delta")
    _axes[1].set_xlabel("|delta|")
    _axes[1].set_ylabel("rows")

    _fig.tight_layout()
    _fig
    return


@app.cell
def _(app_cfg, filtered_df, mo, plt):
    # セル概要: 条件別のズレ集計表と棒グラフを表示する。
    split_col = app_cfg.split_by
    split_summary = (
        filtered_df.groupby(split_col, observed=True)
        .agg(
            rows=("race_id", "size"),
            mean_abs_delta=("abs_delta", "mean"),
            median_abs_delta=("abs_delta", "median"),
            rounded_match_rate=("round_match", "mean"),
            place_rate=("is_place", "mean"),
        )
        .reset_index()
        .sort_values("mean_abs_delta", ascending=False)
    )

    _fig, _axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    _axes[0].bar(split_summary[split_col].astype(str), split_summary["mean_abs_delta"], color="#C44E52")
    _axes[0].set_title(f"Mean abs delta by {split_col}")
    _axes[0].set_xlabel(split_col)
    _axes[0].set_ylabel("mean abs delta")
    _axes[0].tick_params(axis="x", rotation=30)

    _axes[1].bar(split_summary[split_col].astype(str), split_summary["rounded_match_rate"], color="#8172B2")
    _axes[1].set_title(f"Rounded match rate by {split_col}")
    _axes[1].set_xlabel(split_col)
    _axes[1].set_ylabel("match rate")
    _axes[1].tick_params(axis="x", rotation=30)

    _fig.tight_layout()

    mo.vstack(
        [
            mo.md("## 3. Condition Summary"),
            split_summary,
            _fig,
        ]
    )
    return


@app.cell
def _(filtered_df, mo, pd):
    # セル概要: abs delta 別の着順・複勝率サマリを表示する。
    delta_band = pd.cut(
        filtered_df["abs_delta"],
        bins=[-0.001, 0.34, 0.67, 1.00, 3.00],
        labels=["<=0.33", "0.34-0.67", "0.68-1.00", ">1.00"],
    )
    delta_summary = (
        filtered_df.assign(abs_delta_band=delta_band)
        .groupby("abs_delta_band", observed=True)
        .agg(
            rows=("race_id", "size"),
            avg_result_order=("result_order", "mean"),
            place_rate=("is_place", "mean"),
            rounded_match_rate=("round_match", "mean"),
        )
        .reset_index()
    )

    mo.vstack(
        [
            mo.md("## 4. Outcome by |delta| band"),
            delta_summary,
        ]
    )
    return


@app.cell
def _(filtered_df, mo):
    # セル概要: pos4 の avg 比較対象データ件数を表示する。
    _pos4_avg_df = filtered_df.dropna(subset=["actual_corner4_pos", "horse_corner4_avg3"]).copy()
    _lines = [
        "## 5. Pos4 vs Avg3",
        "",
        f"- rows: `{len(_pos4_avg_df):,}`",
        f"- mean abs delta: `{_pos4_avg_df['corner4_avg_abs_delta'].mean():.3f}`",
        f"- median abs delta: `{_pos4_avg_df['corner4_avg_abs_delta'].median():.3f}`",
    ]
    mo.md("\n".join(_lines))
    return


@app.cell
def _(filtered_df, np, plt):
    # セル概要: 実測 pos4 と past-3 avg の関係を 2D 分布と delta 分布で可視化する。
    _pos4_avg_df = filtered_df.dropna(subset=["actual_corner4_pos", "horse_corner4_avg3"]).copy()
    _fig, _axes = plt.subplots(1, 2, figsize=(11.5, 4.0))

    _axes[0].hist2d(
        _pos4_avg_df["actual_corner4_pos"],
        _pos4_avg_df["horse_corner4_avg3"],
        bins=24,
        cmap="Oranges",
    )
    _axes[0].plot([0, 1], [0, 1], linestyle="--", color="black", linewidth=1)
    _axes[0].set_xlabel("actual corner4_pos")
    _axes[0].set_ylabel("horse_corner4_avg3")
    _axes[0].set_title("Actual pos4 vs avg3")

    _axes[1].hist(_pos4_avg_df["corner4_avg_delta"], bins=24, color="#DD8452", edgecolor="white")
    _axes[1].axvline(0.0, color="black", linewidth=1)
    _axes[1].set_xlabel("actual_corner4_pos - horse_corner4_avg3")
    _axes[1].set_ylabel("rows")
    _axes[1].set_title("Pos4 avg delta")

    _fig.tight_layout()
    _fig
    return


@app.cell
def _(app_cfg, filtered_df, mo):
    # セル概要: pos4 avg 差分の条件別サマリを表示する。
    _split_col = app_cfg.split_by
    _summary = (
        filtered_df.dropna(subset=["corner4_avg_abs_delta"])
        .groupby(_split_col, observed=True)
        .agg(
            rows=("race_id", "size"),
            mean_abs_delta=("corner4_avg_abs_delta", "mean"),
            median_abs_delta=("corner4_avg_abs_delta", "median"),
            place_rate=("is_place", "mean"),
        )
        .reset_index()
        .sort_values("mean_abs_delta", ascending=False)
    )
    mo.vstack([mo.md("### Pos4 avg condition summary"), _summary])
    return


@app.cell
def _(filtered_df, mo):
    # セル概要: pos4 の race 内 z 比較対象データ件数を表示する。
    _pos4_z_df = filtered_df.dropna(subset=["actual_corner4_z", "corner4_rate_z"]).copy()
    _lines = [
        "## 6. Pos4 Race-relative Z",
        "",
        f"- rows: `{len(_pos4_z_df):,}`",
        f"- mean abs delta: `{_pos4_z_df['corner4_z_abs_delta'].mean():.3f}`",
        f"- median abs delta: `{_pos4_z_df['corner4_z_abs_delta'].median():.3f}`",
    ]
    mo.md("\n".join(_lines))
    return


@app.cell
def _(filtered_df, plt):
    # セル概要: 実測 pos4 z と feature 側 corner4_rate_z の関係を可視化する。
    _pos4_z_df = filtered_df.dropna(subset=["actual_corner4_z", "corner4_rate_z"]).copy()
    _fig, _axes = plt.subplots(1, 2, figsize=(11.5, 4.0))

    _axes[0].hist2d(
        _pos4_z_df["actual_corner4_z"],
        _pos4_z_df["corner4_rate_z"],
        bins=24,
        cmap="Purples",
    )
    _xy_min = min(_pos4_z_df["actual_corner4_z"].min(), _pos4_z_df["corner4_rate_z"].min())
    _xy_max = max(_pos4_z_df["actual_corner4_z"].max(), _pos4_z_df["corner4_rate_z"].max())
    _axes[0].plot([_xy_min, _xy_max], [_xy_min, _xy_max], linestyle="--", color="black", linewidth=1)
    _axes[0].set_xlabel("actual_corner4_z")
    _axes[0].set_ylabel("corner4_rate_z")
    _axes[0].set_title("Actual pos4 z vs feature z")

    _axes[1].hist(_pos4_z_df["corner4_z_delta"], bins=24, color="#9370DB", edgecolor="white")
    _axes[1].axvline(0.0, color="black", linewidth=1)
    _axes[1].set_xlabel("actual_corner4_z - corner4_rate_z")
    _axes[1].set_ylabel("rows")
    _axes[1].set_title("Pos4 z delta")

    _fig.tight_layout()
    _fig
    return


@app.cell
def _(app_cfg, filtered_df, mo):
    # セル概要: pos4 z 差分の条件別サマリを表示する。
    _split_col = app_cfg.split_by
    _summary = (
        filtered_df.dropna(subset=["corner4_z_abs_delta"])
        .groupby(_split_col, observed=True)
        .agg(
            rows=("race_id", "size"),
            mean_abs_delta=("corner4_z_abs_delta", "mean"),
            median_abs_delta=("corner4_z_abs_delta", "median"),
            place_rate=("is_place", "mean"),
        )
        .reset_index()
        .sort_values("mean_abs_delta", ascending=False)
    )
    mo.vstack([mo.md("### Pos4 z condition summary"), _summary])
    return


if __name__ == "__main__":
    app.run()
