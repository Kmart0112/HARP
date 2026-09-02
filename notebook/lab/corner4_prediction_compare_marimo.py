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
    # セル概要: notebook のタイトルを表示する。
    mo.md(
        "\n".join(
            [
                "# Corner4 Prediction Rule Compare",
                "",
                "- 学習なしの軽量ルールを `corner4_pos` で比較する exploratory notebook",
                "- `p1 / avg / wavg / endpoint trend / OLS / wavg+trend` を横並び評価する",
                "- overall と common support の両方で比較する",
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
        table: str = Field(default="lab.m_corner4_prediction_compare")
        start_date: str = Field(default="2023-01-01")
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        row_limit: int = Field(default=400_000)
        use_cache_default: bool = Field(default=True)
        refresh_db_default: bool = Field(default=False)
        min_num_past3_races: int = Field(default=3)
        surface_filter: str = Field(default="all")
        split_by: str = Field(default="surface")
        rank_metric: str = Field(default="rmse")

    cfg = AppConfig()
    return AppConfig, cfg


@app.cell
def _(cfg, mo):
    # セル概要: データ取得と比較条件の UI を構築する。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    table_widget = mo.ui.text(label="Table", value=cfg.table, full_width=True)
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)
    race_level_min_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_min, label="Race level min")
    race_level_max_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_max, label="Race level max")
    row_limit_widget = mo.ui.number(start=10_000, stop=2_000_000, step=10_000, value=cfg.row_limit, label="Row limit")
    use_cache_widget = mo.ui.switch(value=cfg.use_cache_default, label="Use cache")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_db_default, label="Force refresh DB")
    min_num_past3_widget = mo.ui.number(start=1, stop=3, step=1, value=cfg.min_num_past3_races, label="Min num_past3_races")
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
    rank_metric_widget = mo.ui.dropdown(
        options=["rmse", "mae", "mse", "bias_abs"],
        value=cfg.rank_metric,
        label="Rank metric",
    )
    run_button = mo.ui.run_button(label="Load / Refresh")

    mo.vstack(
        [
            mo.md("## 1. Query / Compare"),
            db_url_widget,
            table_widget,
            mo.hstack([start_date_widget, race_level_min_widget, race_level_max_widget]),
            mo.hstack([row_limit_widget, min_num_past3_widget]),
            mo.hstack([surface_filter_widget, split_by_widget, rank_metric_widget]),
            mo.hstack([use_cache_widget, refresh_db_widget, run_button]),
        ]
    )
    return (
        db_url_widget,
        min_num_past3_widget,
        race_level_max_widget,
        race_level_min_widget,
        rank_metric_widget,
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
    is_script_mode,
    min_num_past3_widget,
    mo,
    race_level_max_widget,
    race_level_min_widget,
    rank_metric_widget,
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
                "min_num_past3_races": int(min_num_past3_widget.value),
                "race_level_max": int(race_level_max_widget.value),
                "race_level_min": int(race_level_min_widget.value),
                "rank_metric": str(rank_metric_widget.value),
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
    predictor_cols = {
        "last1": "pred_last1",
        "avg3": "pred_avg3",
        "wavg3_recent": "pred_wavg3_recent",
        "endpoint_trend3": "pred_endpoint_trend3",
        "ols3_next": "pred_ols3_next",
        "avg5": "pred_avg5",
        "wavg5_recent": "pred_wavg5_recent",
        "endpoint_trend5": "pred_endpoint_trend5",
        "wavg5_plus_trend5": "pred_wavg5_plus_trend5",
    }
    surface_label_map = {0: "turf", 1: "dirt"}

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
        return cache_dir / f"corner4_prediction_compare_{digest}.parquet"

    def to_distance_bucket(distance_m: pd.Series) -> pd.Series:
        return pd.cut(
            distance_m,
            bins=[0, 1400, 1800, 2200, 5000],
            labels=["sprint", "mile", "middle", "long"],
            right=True,
        ).astype("object")

    def build_metrics_df(df: pd.DataFrame, predictors: dict[str, str]) -> pd.DataFrame:
        _rows: list[dict[str, float | int | str]] = []
        for _name, _col in predictors.items():
            _frame = df[["actual_corner4_pos", _col]].dropna()
            if _frame.empty:
                _rows.append(
                    {
                        "predictor": _name,
                        "rows": 0,
                        "mse": float("nan"),
                        "rmse": float("nan"),
                        "mae": float("nan"),
                        "bias": float("nan"),
                        "bias_abs": float("nan"),
                    }
                )
                continue
            _err = _frame["actual_corner4_pos"] - _frame[_col]
            _mse = (_err ** 2).mean()
            _rows.append(
                {
                    "predictor": _name,
                    "rows": int(len(_frame)),
                    "mse": float(_mse),
                    "rmse": float(_mse ** 0.5),
                    "mae": float(_err.abs().mean()),
                    "bias": float(_err.mean()),
                    "bias_abs": float(abs(_err.mean())),
                }
            )
        return pd.DataFrame(_rows)

    return build_metrics_df, make_cache_path, predictor_cols, surface_label_map, to_distance_bucket


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
              actual_corner4_pos,
              num_past3_races,
              num_past5_races,
              pred_last1,
              pred_avg3,
              pred_wavg3_recent,
              pred_endpoint_trend3,
              pred_ols3_next,
              pred_avg5,
              pred_wavg5_recent,
              pred_endpoint_trend5,
              pred_wavg5_plus_trend5
            FROM {app_cfg.table}
            WHERE held_date >= :start_date
              AND race_level BETWEEN :race_level_min AND :race_level_max
              AND actual_corner4_pos IS NOT NULL
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
def _(app_cfg, pd, predictor_cols, raw_df, surface_label_map, to_distance_bucket):
    # セル概要: 可視化に必要な派生列を作り、UI 条件でフィルタする。
    df = raw_df.copy()
    df["held_date"] = pd.to_datetime(df["held_date"])
    df["surface_name"] = df["surface"].map(surface_label_map).fillna(df["surface"].astype(str))
    df["distance_bucket"] = to_distance_bucket(df["distance_m"]).fillna("unknown")
    df["actual_corner4_pos"] = df["actual_corner4_pos"].astype(float)
    for _col in predictor_cols.values():
        df[_col] = df[_col].astype(float)

    filtered_df = df[df["num_past3_races"] >= int(app_cfg.min_num_past3_races)].copy()
    if app_cfg.surface_filter != "all":
        filtered_df = filtered_df[filtered_df["surface"].astype(str) == str(app_cfg.surface_filter)].copy()

    if filtered_df.empty:
        raise ValueError("Filtered dataset is empty. Relax filters and rerun.")
    return (filtered_df,)


@app.cell
def _(build_metrics_df, filtered_df, predictor_cols):
    # セル概要: predictor ごとの overall 指標を計算する。
    available_metrics_df = build_metrics_df(filtered_df, predictor_cols)
    common_support_df = filtered_df.dropna(subset=list(predictor_cols.values())).copy()
    common_metrics_df = build_metrics_df(common_support_df, predictor_cols)
    return available_metrics_df, common_metrics_df, common_support_df


@app.cell
def _(app_cfg, available_metrics_df, common_metrics_df, common_support_df, mo):
    # セル概要: overall 比較結果とベスト predictor を表示する。
    _best = common_metrics_df.sort_values(app_cfg.rank_metric, ascending=True).iloc[0]
    _lines = [
        "## 2. Overall Compare",
        "",
        f"- filtered rows: `{len(common_support_df):,}` on common support",
        f"- best predictor by `{app_cfg.rank_metric}`: `{_best['predictor']}`",
        f"- best {app_cfg.rank_metric}: `{_best[app_cfg.rank_metric]:.4f}`",
    ]
    mo.vstack(
        [
            mo.md("\n".join(_lines)),
            mo.md("### Available rows per predictor"),
            available_metrics_df.sort_values(app_cfg.rank_metric, ascending=True),
            mo.md("### Common support compare"),
            common_metrics_df.sort_values(app_cfg.rank_metric, ascending=True),
        ]
    )
    return


@app.cell
def _(app_cfg, common_metrics_df, plt):
    # セル概要: common support における順位付け指標を棒グラフで描画する。
    _plot_df = common_metrics_df.sort_values(app_cfg.rank_metric, ascending=True).copy()
    _fig = plt.figure(figsize=(11, 4.2))
    _ax = _fig.add_subplot(111)
    _ax.bar(_plot_df["predictor"], _plot_df[app_cfg.rank_metric], color="#4C72B0")
    _ax.set_title(f"Common support {app_cfg.rank_metric} by predictor")
    _ax.set_xlabel("predictor")
    _ax.set_ylabel(app_cfg.rank_metric)
    _ax.tick_params(axis="x", rotation=35)
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(app_cfg, build_metrics_df, common_support_df, mo, predictor_cols):
    # セル概要: 条件別の common support 指標を pivot で表示する。
    _split_col = "surface_name" if app_cfg.split_by == "surface" else app_cfg.split_by
    _rows: list[dict[str, float | int | str]] = []
    for _group_name, _group_df in common_support_df.groupby(_split_col, observed=True):
        _metric_df = build_metrics_df(_group_df, predictor_cols)
        for _record in _metric_df.to_dict("records"):
            _rows.append(
                {
                    app_cfg.split_by: str(_group_name),
                    **_record,
                }
            )
    _split_metrics_df = mo.as_html("")
    import pandas as _pd

    _split_metrics = _pd.DataFrame(_rows)
    _pivot = _split_metrics.pivot(index="predictor", columns=app_cfg.split_by, values=app_cfg.rank_metric)
    mo.vstack(
        [
            mo.md("## 3. Split Compare"),
            _split_metrics.sort_values([app_cfg.split_by, app_cfg.rank_metric], ascending=[True, True]),
            _pivot,
        ]
    )
    return


if __name__ == "__main__":
    app.run()
