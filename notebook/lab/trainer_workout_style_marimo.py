import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebookで利用する依存を読み込む。
    from pathlib import Path
    import sys

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.ticker import PercentFormatter
    from pydantic import BaseModel, Field

    return (
        BaseModel,
        Field,
        Path,
        PercentFormatter,
        TwoSlopeNorm,
        mo,
        np,
        pd,
        plt,
        sys,
    )


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトルートとcache/helperを解決する。
    project_root = Path(__file__).resolve().parents[2]
    src_root = project_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from harp.controllers import build_notebook_config
    from harp.adapters.driven.storage import (
        dataframe_cache_exists,
        load_dataframe_cache,
        resolve_dataframe_cache_path,
    )
    from harp.shared.paths import notebook_analysis_cache_dir

    return (
        build_notebook_config,
        dataframe_cache_exists,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        resolve_dataframe_cache_path,
    )


@app.cell
def _(mo):
    # セル概要: notebookタイトルを表示する。
    mo.md("""
    # Trainer Workout Style Explorer

    厩舎ごとの調教スタイル差を、分布・集計・4F×1Fプロファイルでざっと掴むための notebook。
    """)
    return


@app.cell
def _(mo):
    # セル概要: script実行かinteractive実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, notebook_analysis_cache_dir):
    # セル概要: notebook全体の既定設定を定義する。
    class AppConfig(BaseModel):
        train_year_start: int = Field(default=2013)
        test_year: int = Field(default=2025)
        main_parquet_path: str = Field(default="")
        start_date: str = Field(default="2023-01-01")
        end_date: str = Field(default="")
        min_samples: int = Field(default=80)
        top_n_trainers: int = Field(default=20)
        sort_by: str = Field(default="starts")

    cfg = AppConfig(
        main_parquet_path=str(
            notebook_analysis_cache_dir() / "m_train_race_horse_past5_2013_2025.parquet"
        )
    )
    return (cfg,)


@app.cell
def _(cfg, mo):
    # セル概要: interactive実行用の設定UIを表示する。
    parquet_path_widget = mo.ui.text(
        label="Main parquet path",
        value=cfg.main_parquet_path,
        full_width=True,
    )
    start_date_widget = mo.ui.text(
        label="Start date",
        value=cfg.start_date,
        placeholder="YYYY-MM-DD",
    )
    end_date_widget = mo.ui.text(
        label="End date",
        value=cfg.end_date,
        placeholder="YYYY-MM-DD or blank",
    )
    min_samples_widget = mo.ui.number(
        start=10,
        stop=500,
        step=10,
        value=cfg.min_samples,
        label="Min samples per trainer",
    )
    top_n_widget = mo.ui.number(
        start=5,
        stop=40,
        step=1,
        value=cfg.top_n_trainers,
        label="Top trainers to plot",
    )
    sort_by_widget = mo.ui.dropdown(
        options={
            "starts": "starts",
            "current_wood_z_median": "current_wood_z_median",
            "current_hanro_z_median": "current_hanro_z_median",
            "trainer_place_rate_5y_median": "trainer_place_rate_5y_median",
        },
        value=cfg.sort_by,
        label="Trainer ordering",
    )
    mo.vstack(
        [
            parquet_path_widget,
            mo.hstack([start_date_widget, end_date_widget]),
            mo.hstack([min_samples_widget, top_n_widget, sort_by_widget]),
        ]
    )
    return (
        end_date_widget,
        min_samples_widget,
        parquet_path_widget,
        sort_by_widget,
        start_date_widget,
        top_n_widget,
    )


@app.cell
def _(
    build_notebook_config,
    cfg,
    end_date_widget,
    is_script_mode,
    min_samples_widget,
    mo,
    parquet_path_widget,
    sort_by_widget,
    start_date_widget,
    top_n_widget,
):
    # セル概要: UI/CLI設定を単一の設定オブジェクトへ正規化する。
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
                "main_parquet_path": str(parquet_path_widget.value).strip(),
                "start_date": str(start_date_widget.value).strip(),
                "end_date": str(end_date_widget.value).strip(),
                "min_samples": int(min_samples_widget.value),
                "top_n_trainers": int(top_n_widget.value),
                "sort_by": str(sort_by_widget.value),
            },
        )

    if not resolved_cfg.main_parquet_path:
        raise ValueError("main_parquet_path is required.")
    if resolved_cfg.min_samples <= 0:
        raise ValueError("min_samples must be positive.")
    if resolved_cfg.top_n_trainers <= 0:
        raise ValueError("top_n_trainers must be positive.")
    return (resolved_cfg,)


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 設定の要約を表示する。
    mo.md("""
    ## 1. データ読み込み
    """)
    return


@app.cell
def _(Path, resolved_cfg):
    # セル概要: parquet pathをPathへ変換する。
    cache_path = Path(resolved_cfg.main_parquet_path).expanduser()
    return (cache_path,)


@app.cell
def _(
    cache_path,
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
):
    # セル概要: parquet cacheを読み込む。
    if not dataframe_cache_exists(cache_path):
        raise ValueError(
            "Main parquet not found.\n"
            f"missing_path={cache_path}\n"
            "Run scripts/refresh_analysis_cache.sh before opening this notebook."
        )

    resolved_path = resolve_dataframe_cache_path(cache_path)
    print(f"[cache] loading from {resolved_path}")
    df = load_dataframe_cache(cache_path)
    return df, resolved_path


@app.cell
def _(np, pd):
    # セル概要: notebook内で利用する小さな集計helperを定義する。
    metric_columns = {
        "current_wood_z_median": "wood_lap_time_1_z_tozai_day",
        "current_hanro_z_median": "hanro_lap_time_1_z_tozai_day",
        "week1_wood_z_median": "week1_wood_lap_time_1_z_tozai_day",
        "week1_hanro_z_median": "week1_hanro_lap_time_1_z_tozai_day",
        "current_wood_accel_rate": "wood_accel_flag",
        "current_hanro_accel_rate": "hanro_accel_flag",
        "week1_wood_accel_rate": "week1_wood_accel_flag",
        "week1_hanro_accel_rate": "week1_hanro_accel_flag",
        "current_wood_late_sharpness_median": "wood_late_sharpness",
        "current_hanro_late_sharpness_median": "hanro_late_sharpness",
        "week1_wood_late_sharpness_median": "week1_wood_late_sharpness",
        "week1_hanro_late_sharpness_median": "week1_hanro_late_sharpness",
        "trainer_place_rate_5y_median": "trainer_place_rate_5y",
    }

    def _normalize_date(value: str) -> pd.Timestamp | None:
        candidate = str(value).strip()
        if not candidate:
            return None
        return pd.to_datetime(candidate)

    def build_filtered_frame(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        required = [
            "trainer_cd",
            "held_date",
            "is_place",
            "is_win",
            "odds_tansho",
            "wood_lap_time_1_z_tozai_day",
            "hanro_lap_time_1_z_tozai_day",
            "week1_wood_lap_time_1_z_tozai_day",
            "week1_hanro_lap_time_1_z_tozai_day",
            "wood_accel_flag",
            "hanro_accel_flag",
            "week1_wood_accel_flag",
            "week1_hanro_accel_flag",
            "wood_late_sharpness",
            "hanro_late_sharpness",
            "week1_wood_late_sharpness",
            "week1_hanro_late_sharpness",
            "wood_4f1f_profile_cat3",
            "hanro_4f1f_profile_cat3",
            "trainer_place_rate_5y",
        ]
        filtered = frame.loc[:, required].copy()
        filtered = filtered.loc[filtered["trainer_cd"].notna()].copy()
        filtered["trainer_cd"] = filtered["trainer_cd"].astype("Int64").astype(str)
        filtered["held_date"] = pd.to_datetime(filtered["held_date"], errors="coerce")
        filtered["is_place"] = pd.to_numeric(filtered["is_place"], errors="coerce").fillna(0.0)
        filtered["is_win"] = pd.to_numeric(filtered["is_win"], errors="coerce").fillna(0.0)
        filtered["odds_tansho"] = pd.to_numeric(filtered["odds_tansho"], errors="coerce")

        start_ts = _normalize_date(start_date)
        end_ts = _normalize_date(end_date)
        if start_ts is not None:
            filtered = filtered.loc[filtered["held_date"] >= start_ts].copy()
        if end_ts is not None:
            filtered = filtered.loc[filtered["held_date"] <= end_ts].copy()
        return filtered

    def build_trainer_summary(frame: pd.DataFrame) -> pd.DataFrame:
        grouped = frame.groupby("trainer_cd", dropna=False)
        summary = grouped.size().rename("starts").to_frame()
        for output_name, source_col in metric_columns.items():
            if output_name.endswith("_rate"):
                summary[output_name] = grouped[source_col].mean()
            else:
                summary[output_name] = grouped[source_col].median()
        summary["missing_current_wood_rate"] = grouped["wood_lap_time_1_z_tozai_day"].apply(
            lambda s: float(s.isna().mean())
        )
        summary["missing_current_hanro_rate"] = grouped["hanro_lap_time_1_z_tozai_day"].apply(
            lambda s: float(s.isna().mean())
        )
        return summary.reset_index()

    def build_profile_share(frame: pd.DataFrame, source_col: str) -> pd.DataFrame:
        profile = frame.loc[frame[source_col].notna(), ["trainer_cd", source_col]].copy()
        profile[source_col] = profile[source_col].astype("Int64")
        profile = profile.loc[profile[source_col] > 0].copy()
        if profile.empty:
            return pd.DataFrame()

        pivot = (
            pd.crosstab(profile["trainer_cd"], profile[source_col], normalize="index")
            .reindex(columns=list(range(1, 10)), fill_value=0.0)
            .sort_index(axis=1)
        )
        pivot.columns = [f"cat{int(col)}" for col in pivot.columns]
        return pivot

    def build_boxplot_series(frame: pd.DataFrame, trainer_ids: list[str], value_col: str) -> list[np.ndarray]:
        series_list: list[np.ndarray] = []
        for trainer_id in trainer_ids:
            values = frame.loc[frame["trainer_cd"] == trainer_id, value_col].dropna().to_numpy()
            series_list.append(values)
        return series_list

    def _make_qbucket(series: pd.Series, q: int = 10) -> pd.Series:
        ranked = series.rank(method="first")
        return pd.qcut(ranked, q=q, labels=False, duplicates="drop") + 1

    def build_pattern_signal_frame(frame: pd.DataFrame, trainer_summary_frame: pd.DataFrame) -> pd.DataFrame:
        baseline_cols = [
            "trainer_cd",
            "current_wood_z_median",
            "current_hanro_z_median",
            "week1_wood_z_median",
            "week1_hanro_z_median",
            "current_wood_late_sharpness_median",
            "current_hanro_late_sharpness_median",
            "week1_wood_late_sharpness_median",
            "week1_hanro_late_sharpness_median",
        ]
        enriched = frame.merge(
            trainer_summary_frame.loc[:, baseline_cols],
            on="trainer_cd",
            how="left",
        )

        residual_pairs = {
            "current_wood_resid": ("wood_lap_time_1_z_tozai_day", "current_wood_z_median"),
            "current_hanro_resid": ("hanro_lap_time_1_z_tozai_day", "current_hanro_z_median"),
            "week1_wood_resid": ("week1_wood_lap_time_1_z_tozai_day", "week1_wood_z_median"),
            "week1_hanro_resid": ("week1_hanro_lap_time_1_z_tozai_day", "week1_hanro_z_median"),
        }
        residual_cols: list[str] = []
        for output_col, (value_col, base_col) in residual_pairs.items():
            enriched[output_col] = enriched[value_col] - enriched[base_col]
            residual_cols.append(output_col)

        enriched["pattern_match_score"] = -enriched.loc[:, residual_cols].abs().mean(axis=1, skipna=True)
        enriched["pattern_fast_score"] = -enriched.loc[:, residual_cols].mean(axis=1, skipna=True)
        enriched["usable_residual_dims"] = enriched.loc[:, residual_cols].notna().sum(axis=1)
        enriched = enriched.loc[enriched["usable_residual_dims"] >= 2].copy()

        sharpness_residual_pairs = {
            "current_wood_sharp_resid": ("wood_late_sharpness", "current_wood_late_sharpness_median"),
            "current_hanro_sharp_resid": ("hanro_late_sharpness", "current_hanro_late_sharpness_median"),
            "week1_wood_sharp_resid": ("week1_wood_late_sharpness", "week1_wood_late_sharpness_median"),
            "week1_hanro_sharp_resid": ("week1_hanro_late_sharpness", "week1_hanro_late_sharpness_median"),
        }
        sharpness_residual_cols: list[str] = []
        for output_col, (value_col, base_col) in sharpness_residual_pairs.items():
            enriched[output_col] = enriched[value_col] - enriched[base_col]
            sharpness_residual_cols.append(output_col)

        enriched["sharpness_match_score"] = -enriched.loc[:, sharpness_residual_cols].abs().mean(
            axis=1,
            skipna=True,
        )
        enriched["sharpness_up_score"] = enriched.loc[:, sharpness_residual_cols].mean(
            axis=1,
            skipna=True,
        )
        enriched["usable_sharpness_dims"] = enriched.loc[:, sharpness_residual_cols].notna().sum(axis=1)
        enriched = enriched.loc[enriched["usable_sharpness_dims"] >= 2].copy()

        odds_series = enriched["odds_tansho"].clip(lower=0)
        enriched["odds_log_inv"] = -np.log1p(odds_series)
        enriched["odds_bucket"] = _make_qbucket(enriched["odds_log_inv"], q=10)
        odds_expectation = (
            enriched.groupby("odds_bucket", dropna=True)["is_place"].mean().rename("expected_place_by_odds")
        )
        enriched = enriched.merge(odds_expectation, on="odds_bucket", how="left")
        enriched["excess_place_vs_odds"] = enriched["is_place"] - enriched["expected_place_by_odds"]
        enriched["match_bucket"] = _make_qbucket(enriched["pattern_match_score"], q=10)
        enriched["fast_bucket"] = _make_qbucket(enriched["pattern_fast_score"], q=10)
        enriched["sharp_match_bucket"] = _make_qbucket(enriched["sharpness_match_score"], q=10)
        enriched["sharp_up_bucket"] = _make_qbucket(enriched["sharpness_up_score"], q=10)
        return enriched

    def summarize_bucket(
        frame: pd.DataFrame,
        bucket_col: str,
        *,
        match_score_col: str,
        effect_score_col: str,
    ) -> pd.DataFrame:
        summary = (
            frame.groupby(bucket_col, dropna=True)
            .agg(
                starts=("is_place", "size"),
                place_rate=("is_place", "mean"),
                win_rate=("is_win", "mean"),
                excess_place_vs_odds=("excess_place_vs_odds", "mean"),
                median_odds_tansho=("odds_tansho", "median"),
                mean_match_score=(match_score_col, "mean"),
                mean_effect_score=(effect_score_col, "mean"),
            )
            .reset_index()
            .sort_values(bucket_col)
        )
        return summary

    def summarize_match_fast_heatmap(frame: pd.DataFrame, *, match_bucket_col: str, effect_bucket_col: str) -> pd.DataFrame:
        heatmap = (
            frame.groupby([match_bucket_col, effect_bucket_col], dropna=True)
            .agg(
                starts=("is_place", "size"),
                place_rate=("is_place", "mean"),
                excess_place_vs_odds=("excess_place_vs_odds", "mean"),
            )
            .reset_index()
        )
        return heatmap

    return (
        build_boxplot_series,
        build_filtered_frame,
        build_pattern_signal_frame,
        build_profile_share,
        build_trainer_summary,
        summarize_bucket,
        summarize_match_fast_heatmap,
    )


@app.cell
def _(build_filtered_frame, df, resolved_cfg):
    # セル概要: 期間条件を反映した分析対象データを作る。
    filtered_df = build_filtered_frame(
        df,
        start_date=resolved_cfg.start_date,
        end_date=resolved_cfg.end_date,
    )
    return (filtered_df,)


@app.cell
def _(build_trainer_summary, filtered_df, resolved_cfg):
    # セル概要: 厩舎単位の集計表を作る。
    trainer_summary_all = build_trainer_summary(filtered_df)
    trainer_summary = (
        trainer_summary_all.loc[trainer_summary_all["starts"] >= resolved_cfg.min_samples]
        .sort_values(
            by=[resolved_cfg.sort_by, "starts"],
            ascending=[False, False],
            kind="mergesort",
        )
        .head(resolved_cfg.top_n_trainers)
        .reset_index(drop=True)
    )
    return trainer_summary, trainer_summary_all


@app.cell
def _(mo, resolved_cfg, resolved_path, trainer_summary, trainer_summary_all):
    # セル概要: フィルタ条件と対象厩舎数を表示する。
    mo.md(
        f"""
        - source: `{resolved_path}`
        - start_date: `{resolved_cfg.start_date or "none"}`
        - end_date: `{resolved_cfg.end_date or "none"}`
        - eligible_trainers: `{len(trainer_summary_all):,}`
        - plotted_trainers: `{len(trainer_summary):,}`
        - min_samples: `{resolved_cfg.min_samples}`
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 生データと上位厩舎一覧のプレビュー見出しを表示する。
    mo.md("""
    ## 2. 集計プレビュー
    """)
    return


@app.cell
def _(filtered_df):
    # セル概要: 分析対象データの先頭を確認する。
    filtered_df.head(10)
    return


@app.cell
def _(trainer_summary):
    # セル概要: 厩舎別集計の主要列を確認する。
    _preview_cols_trainer = [
        "trainer_cd",
        "starts",
        "current_wood_z_median",
        "current_hanro_z_median",
        "week1_wood_z_median",
        "week1_hanro_z_median",
        "current_wood_accel_rate",
        "current_hanro_accel_rate",
        "trainer_place_rate_5y_median",
    ]
    trainer_summary.loc[:, _preview_cols_trainer].round(3)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 分布図の見出しを表示する。
    mo.md("""
    ## 3. 厩舎別の調教分布
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 分布図の読み方を説明する。
    mo.md("""
    この図は、各厩舎がその期間にどのくらい速い調教をしやすいかを、`z_tozai_day` の分布で見ています。

    - 赤い破線の `0` は、その日・その東西区分の平均的な位置です。
    - 左に寄るほど、その日の中で速めの調教が多い厩舎です。
    - 箱が狭い厩舎は型が安定していて、広い厩舎は馬や状況によって調整幅が大きいと読めます。
    - `current` と `week1` を見比べると、直前で強める厩舎か、一週前に負荷をかける厩舎かの違いも見えます。
    """)
    return


@app.cell
def _(build_boxplot_series, filtered_df, np, plt, trainer_summary):
    # セル概要: current/week1 の wood/hanro z-score 分布を厩舎別boxplotで描く。
    plot_specs = [
        ("wood_lap_time_1_z_tozai_day", "Current wood 1F z"),
        ("hanro_lap_time_1_z_tozai_day", "Current hanro 1F z"),
        ("week1_wood_lap_time_1_z_tozai_day", "Week1 wood 1F z"),
        ("week1_hanro_lap_time_1_z_tozai_day", "Week1 hanro 1F z"),
    ]
    trainer_ids = trainer_summary["trainer_cd"].tolist()

    _fig_box, _axes_box = plt.subplots(
        2, 2, figsize=(16, max(8, len(trainer_ids) * 0.35)), sharex=False
    )
    for _ax_box, (value_col, _title_box) in zip(_axes_box.flatten(), plot_specs, strict=False):
        series_list = build_boxplot_series(filtered_df, trainer_ids, value_col)
        positions = np.arange(1, len(trainer_ids) + 1)
        _ax_box.boxplot(
            series_list,
            vert=False,
            tick_labels=trainer_ids,
            positions=positions,
            patch_artist=True,
            showfliers=False,
            boxprops={"facecolor": "#8ecae6", "alpha": 0.75},
            medianprops={"color": "#023047", "linewidth": 1.6},
        )
        _ax_box.axvline(0.0, color="#d62828", linestyle="--", linewidth=1.0)
        _ax_box.set_title(_title_box)
        _ax_box.set_xlabel("z-score")
        _ax_box.set_ylabel("trainer_cd")

    _fig_box.tight_layout()
    _fig_box
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: スタイルheatmapの見出しを表示する。
    mo.md("""
    ## 4. 厩舎スタイル heatmap
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: スタイルheatmapの読み方を説明する。
    mo.md("""
    この heatmap は、厩舎ごとの代表的な調教スタイルを列ごとに標準化して比較したものです。

    - 赤いセルは、その指標が他厩舎より高い側にあることを示します。
    - 青いセルは、その指標が他厩舎より低い側にあることを示します。
    - `*_z_median` は速い遅い、`*_accel_rate` は加速型か、`*_late_sharpness_median` は終い重点かを見る軸です。
    - 横に眺めると「その厩舎らしさ」、縦に眺めると「どの指標で差がついているか」が分かります。
    """)
    return


@app.cell
def _(TwoSlopeNorm, np, plt, trainer_summary):
    # セル概要: 厩舎ごとの調教スタイル集計をz標準化してheatmapで描く。
    metric_cols = [
        "current_wood_z_median",
        "current_hanro_z_median",
        "week1_wood_z_median",
        "week1_hanro_z_median",
        "current_wood_accel_rate",
        "current_hanro_accel_rate",
        "week1_wood_accel_rate",
        "week1_hanro_accel_rate",
        "current_wood_late_sharpness_median",
        "current_hanro_late_sharpness_median",
        "trainer_place_rate_5y_median",
    ]
    metric_df = trainer_summary.set_index("trainer_cd").loc[:, metric_cols]
    centered = metric_df.apply(
        lambda col: (col - col.mean()) / col.std(ddof=0) if col.std(ddof=0) > 0 else 0.0
    )
    centered = centered.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    _fig_heatmap, _ax_heatmap = plt.subplots(figsize=(14, max(6, len(centered) * 0.45)))
    norm = TwoSlopeNorm(vmin=-2.5, vcenter=0.0, vmax=2.5)
    _im_heatmap = _ax_heatmap.imshow(centered.to_numpy(), aspect="auto", cmap="coolwarm", norm=norm)
    _ax_heatmap.set_yticks(range(len(centered.index)))
    _ax_heatmap.set_yticklabels(centered.index)
    _ax_heatmap.set_xticks(range(len(centered.columns)))
    _ax_heatmap.set_xticklabels(centered.columns, rotation=45, ha="right")
    _ax_heatmap.set_title("Trainer style heatmap (column-wise z-score)")
    _fig_heatmap.colorbar(_im_heatmap, ax=_ax_heatmap, fraction=0.025, pad=0.02)
    _fig_heatmap.tight_layout()
    _fig_heatmap
    return (centered,)


@app.cell
def _(centered):
    # セル概要: heatmapの元になったz標準化表を確認する。
    centered.round(2)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: プロファイル分布の見出しを表示する。
    mo.md("""
    ## 5. 4F×1F profile 分布
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: プロファイル分布の読み方を説明する。
    mo.md("""
    ここでは、厩舎ごとにどの 4F×1F profile category をどのくらい使っているかを構成比で見ています。

    - 色が濃いカテゴリほど、その厩舎がよく使う調教パターンです。
    - 一部カテゴリに強く偏る厩舎は、調教の型がはっきりしています。
    - 広く散る厩舎は、馬ごとに負荷の掛け方を変えている可能性があります。
    - `wood` と `hanro` を並べて見ると、コース別の使い分けも追えます。
    """)
    return


@app.cell
def _(build_profile_share, filtered_df, trainer_summary):
    # セル概要: 4F×1F profile category の厩舎別構成比を計算する。
    selected_trainers = trainer_summary["trainer_cd"].tolist()
    selected_df = filtered_df.loc[filtered_df["trainer_cd"].isin(selected_trainers)].copy()
    wood_profile_share = build_profile_share(selected_df, "wood_4f1f_profile_cat3").reindex(
        selected_trainers
    )
    hanro_profile_share = build_profile_share(selected_df, "hanro_4f1f_profile_cat3").reindex(
        selected_trainers
    )
    return hanro_profile_share, wood_profile_share


@app.cell
def _(PercentFormatter, hanro_profile_share, plt, wood_profile_share):
    # セル概要: wood/hanro profile構成比をheatmapで描く。
    _fig_profile, _axes_profile = plt.subplots(
        1, 2, figsize=(16, max(6, len(wood_profile_share) * 0.4))
    )
    profile_specs = [
        (wood_profile_share, "Wood 4F×1F profile share"),
        (hanro_profile_share, "Hanro 4F×1F profile share"),
    ]

    for _ax_profile, (profile_df, _title_profile) in zip(
        _axes_profile, profile_specs, strict=False
    ):
        if profile_df.empty:
            _ax_profile.set_title(f"{_title_profile}\n(no data)")
            _ax_profile.axis("off")
            continue
        _im_profile = _ax_profile.imshow(
            profile_df.fillna(0.0).to_numpy(),
            aspect="auto",
            cmap="YlGnBu",
            vmin=0.0,
            vmax=1.0,
        )
        _ax_profile.set_yticks(range(len(profile_df.index)))
        _ax_profile.set_yticklabels(profile_df.index)
        _ax_profile.set_xticks(range(len(profile_df.columns)))
        _ax_profile.set_xticklabels(profile_df.columns)
        _ax_profile.set_title(_title_profile)
        _cbar_profile = _fig_profile.colorbar(
            _im_profile, ax=_ax_profile, fraction=0.046, pad=0.03
        )
        _cbar_profile.ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    _fig_profile.tight_layout()
    _fig_profile
    return


@app.cell
def _(hanro_profile_share, wood_profile_share):
    # セル概要: profile構成比の表を確認する。
    {
        "wood_profile_share": wood_profile_share.round(3),
        "hanro_profile_share": hanro_profile_share.round(3),
    }
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 成績との関係の見出しを表示する。
    mo.md("""
    ## 6. 厩舎パターンと成績の関係
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 厩舎パターンと成績の関係の読み方を説明する。
    mo.md("""
    ここでは、各馬の調教が「厩舎のいつもの型に合っているか」と「厩舎のいつもの型より速いか」を成績とつなげて見ます。

    - `pattern_match_score` は、厩舎中央値からのズレが小さいほど高くなります。
    - `pattern_fast_score` は、厩舎中央値より速い側に寄るほど高くなります。
    - 折れ線の `place_rate` は単純な複勝率です。
    - 棒の `excess_place_vs_odds` は、単勝オッズ帯で見た期待値との差で、人気補正を少しだけ入れた見方です。
    - 一致度が効くなら「厩舎型に合う馬が走る」、速さが効くなら「厩舎基準を超える動き自体に意味がある」と読めます。
    """)
    return


@app.cell
def _(build_pattern_signal_frame, filtered_df, trainer_summary_all):
    # セル概要: 厩舎パターンとの一致度と超過スピードを馬単位で計算する。
    pattern_signal_df = build_pattern_signal_frame(filtered_df, trainer_summary_all)
    return (pattern_signal_df,)


@app.cell
def _(pattern_signal_df):
    # セル概要: 行単位のシグナル列を確認する。
    _preview_cols_signal = [
        "trainer_cd",
        "is_place",
        "odds_tansho",
        "pattern_match_score",
        "pattern_fast_score",
        "excess_place_vs_odds",
        "match_bucket",
        "fast_bucket",
    ]
    pattern_signal_df.loc[:, _preview_cols_signal].head(10).round(3)
    return


@app.cell
def _(pattern_signal_df, summarize_bucket):
    # セル概要: 一致度decileごとの成績集計を作る。
    match_bucket_summary = summarize_bucket(
        pattern_signal_df,
        "match_bucket",
        match_score_col="pattern_match_score",
        effect_score_col="pattern_fast_score",
    )
    return (match_bucket_summary,)


@app.cell
def _(pattern_signal_df, summarize_bucket):
    # セル概要: 超過スピードdecileごとの成績集計を作る。
    fast_bucket_summary = summarize_bucket(
        pattern_signal_df,
        "fast_bucket",
        match_score_col="pattern_match_score",
        effect_score_col="pattern_fast_score",
    )
    return (fast_bucket_summary,)


@app.cell
def _(pattern_signal_df, summarize_match_fast_heatmap):
    # セル概要: 一致度×超過スピードの二次元集計を作る。
    match_fast_heatmap_summary = summarize_match_fast_heatmap(
        pattern_signal_df,
        match_bucket_col="match_bucket",
        effect_bucket_col="fast_bucket",
    )
    return (match_fast_heatmap_summary,)


@app.cell
def _(fast_bucket_summary, match_bucket_summary, plt):
    # セル概要: 一致度と超過スピードのdecile別成績を描く。
    _fig_signal, _axes_signal = plt.subplots(2, 2, figsize=(14, 10), sharex="col")

    _axes_signal[0, 0].plot(
        match_bucket_summary["match_bucket"],
        match_bucket_summary["place_rate"],
        marker="o",
        color="#1d3557",
    )
    _axes_signal[0, 0].set_title("Pattern match score vs place rate")
    _axes_signal[0, 0].set_ylabel("place_rate")

    _axes_signal[1, 0].bar(
        match_bucket_summary["match_bucket"],
        match_bucket_summary["excess_place_vs_odds"],
        color="#457b9d",
    )
    _axes_signal[1, 0].axhline(0.0, color="#d62828", linestyle="--", linewidth=1.0)
    _axes_signal[1, 0].set_title("Pattern match score vs excess place rate")
    _axes_signal[1, 0].set_xlabel("match decile (10 = most matched)")
    _axes_signal[1, 0].set_ylabel("excess vs odds")

    _axes_signal[0, 1].plot(
        fast_bucket_summary["fast_bucket"],
        fast_bucket_summary["place_rate"],
        marker="o",
        color="#2a9d8f",
    )
    _axes_signal[0, 1].set_title("Faster-than-pattern score vs place rate")
    _axes_signal[0, 1].set_ylabel("place_rate")

    _axes_signal[1, 1].bar(
        fast_bucket_summary["fast_bucket"],
        fast_bucket_summary["excess_place_vs_odds"],
        color="#52b788",
    )
    _axes_signal[1, 1].axhline(0.0, color="#d62828", linestyle="--", linewidth=1.0)
    _axes_signal[1, 1].set_title("Faster-than-pattern score vs excess place rate")
    _axes_signal[1, 1].set_xlabel("fast decile (10 = faster than stable norm)")
    _axes_signal[1, 1].set_ylabel("excess vs odds")

    _fig_signal.tight_layout()
    _fig_signal
    return


@app.cell
def _(TwoSlopeNorm, match_fast_heatmap_summary, np, plt):
    # セル概要: 一致度×超過スピードの二次元成績heatmapを描く。
    _place_matrix = (
        match_fast_heatmap_summary.pivot(
            index="match_bucket",
            columns="fast_bucket",
            values="place_rate",
        )
        .reindex(index=range(1, 11), columns=range(1, 11))
    )
    _excess_matrix = (
        match_fast_heatmap_summary.pivot(
            index="match_bucket",
            columns="fast_bucket",
            values="excess_place_vs_odds",
        )
        .reindex(index=range(1, 11), columns=range(1, 11))
    )

    _fig_joint, _axes_joint = plt.subplots(1, 2, figsize=(15, 6))
    _im_place = _axes_joint[0].imshow(_place_matrix.to_numpy(), aspect="auto", cmap="YlOrRd")
    _axes_joint[0].set_title("Place rate by match x fast decile")
    _axes_joint[0].set_xlabel("fast decile")
    _axes_joint[0].set_ylabel("match decile")
    _axes_joint[0].set_xticks(range(10))
    _axes_joint[0].set_xticklabels(range(1, 11))
    _axes_joint[0].set_yticks(range(10))
    _axes_joint[0].set_yticklabels(range(1, 11))
    _fig_joint.colorbar(_im_place, ax=_axes_joint[0], fraction=0.046, pad=0.03)

    _norm_excess = TwoSlopeNorm(
        vmin=float(np.nanmin(_excess_matrix.to_numpy())),
        vcenter=0.0,
        vmax=float(np.nanmax(_excess_matrix.to_numpy())),
    )
    _im_excess = _axes_joint[1].imshow(
        _excess_matrix.to_numpy(),
        aspect="auto",
        cmap="coolwarm",
        norm=_norm_excess,
    )
    _axes_joint[1].set_title("Excess place vs odds by match x fast decile")
    _axes_joint[1].set_xlabel("fast decile")
    _axes_joint[1].set_ylabel("match decile")
    _axes_joint[1].set_xticks(range(10))
    _axes_joint[1].set_xticklabels(range(1, 11))
    _axes_joint[1].set_yticks(range(10))
    _axes_joint[1].set_yticklabels(range(1, 11))
    _fig_joint.colorbar(_im_excess, ax=_axes_joint[1], fraction=0.046, pad=0.03)

    _fig_joint.tight_layout()
    _fig_joint
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 二次元heatmapの読み方を補足する。
    mo.md("""
    二次元 heatmap では、縦が「厩舎パターンへの一致度」、横が「厩舎パターンより速いか」を表します。

    - 右上が強ければ、「厩舎の型に合っていて、なおかつ速い」馬が走りやすい形です。
    - 左上が強ければ、「厩舎の型には合うが、速すぎない方がよい」可能性があります。
    - 右下が強ければ、「型からは外れても、速さの上積みが効く」形です。
    """)
    return


@app.cell
def _(fast_bucket_summary, match_bucket_summary):
    # セル概要: decile集計表を確認する。
    {
        "match_bucket_summary": match_bucket_summary.round(4),
        "fast_bucket_summary": fast_bucket_summary.round(4),
    }
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: sharpness関係の見出しを表示する。
    mo.md("""
    ## 7. 厩舎 sharpness パターンと成績の関係
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: sharpness関係の読み方を説明する。
    mo.md("""
    こちらは速さそのものではなく、`late_sharpness` を使って「終い重点の度合い」が厩舎パターンとどう関係するかを見ています。

    - `sharpness_match_score` は、厩舎のいつもの終い重点パターンにどれだけ近いかです。
    - `sharpness_up_score` は、厩舎のいつもより終いが sharper かどうかです。
    - ここが効くなら、単純な時計よりも「終いの作り方」が成績に効いている可能性があります。
    - 特に `excess_place_vs_odds` で差が出るなら、市場が拾い切れていない終いの良さがあるかもしれません。
    """)
    return


@app.cell
def _(pattern_signal_df):
    # セル概要: sharpness系シグナル列を確認する。
    _preview_cols_sharp = [
        "trainer_cd",
        "wood_late_sharpness",
        "hanro_late_sharpness",
        "sharpness_match_score",
        "sharpness_up_score",
        "sharp_match_bucket",
        "sharp_up_bucket",
        "excess_place_vs_odds",
    ]
    pattern_signal_df.loc[:, _preview_cols_sharp].head(10).round(3)
    return


@app.cell
def _(pattern_signal_df, summarize_bucket):
    # セル概要: sharpness一致度decileごとの成績集計を作る。
    sharp_match_bucket_summary = summarize_bucket(
        pattern_signal_df,
        "sharp_match_bucket",
        match_score_col="sharpness_match_score",
        effect_score_col="sharpness_up_score",
    )
    return (sharp_match_bucket_summary,)


@app.cell
def _(pattern_signal_df, summarize_bucket):
    # セル概要: 厩舎基準よりsharperかのdecileごとの成績集計を作る。
    sharp_up_bucket_summary = summarize_bucket(
        pattern_signal_df,
        "sharp_up_bucket",
        match_score_col="sharpness_match_score",
        effect_score_col="sharpness_up_score",
    )
    return (sharp_up_bucket_summary,)


@app.cell
def _(pattern_signal_df, summarize_match_fast_heatmap):
    # セル概要: sharpness一致度×sharper度の二次元集計を作る。
    sharp_joint_heatmap_summary = summarize_match_fast_heatmap(
        pattern_signal_df,
        match_bucket_col="sharp_match_bucket",
        effect_bucket_col="sharp_up_bucket",
    )
    return (sharp_joint_heatmap_summary,)


@app.cell
def _(plt, sharp_match_bucket_summary, sharp_up_bucket_summary):
    # セル概要: sharpness一致度とsharper度のdecile別成績を描く。
    _fig_sharp_signal, _axes_sharp_signal = plt.subplots(2, 2, figsize=(14, 10), sharex="col")

    _axes_sharp_signal[0, 0].plot(
        sharp_match_bucket_summary["sharp_match_bucket"],
        sharp_match_bucket_summary["place_rate"],
        marker="o",
        color="#6a4c93",
    )
    _axes_sharp_signal[0, 0].set_title("Sharpness match score vs place rate")
    _axes_sharp_signal[0, 0].set_ylabel("place_rate")

    _axes_sharp_signal[1, 0].bar(
        sharp_match_bucket_summary["sharp_match_bucket"],
        sharp_match_bucket_summary["excess_place_vs_odds"],
        color="#8d99ae",
    )
    _axes_sharp_signal[1, 0].axhline(0.0, color="#d62828", linestyle="--", linewidth=1.0)
    _axes_sharp_signal[1, 0].set_title("Sharpness match score vs excess place rate")
    _axes_sharp_signal[1, 0].set_xlabel("sharp match decile (10 = most matched)")
    _axes_sharp_signal[1, 0].set_ylabel("excess vs odds")

    _axes_sharp_signal[0, 1].plot(
        sharp_up_bucket_summary["sharp_up_bucket"],
        sharp_up_bucket_summary["place_rate"],
        marker="o",
        color="#c77dff",
    )
    _axes_sharp_signal[0, 1].set_title("Sharper-than-pattern score vs place rate")
    _axes_sharp_signal[0, 1].set_ylabel("place_rate")

    _axes_sharp_signal[1, 1].bar(
        sharp_up_bucket_summary["sharp_up_bucket"],
        sharp_up_bucket_summary["excess_place_vs_odds"],
        color="#b5179e",
    )
    _axes_sharp_signal[1, 1].axhline(0.0, color="#d62828", linestyle="--", linewidth=1.0)
    _axes_sharp_signal[1, 1].set_title("Sharper-than-pattern score vs excess place rate")
    _axes_sharp_signal[1, 1].set_xlabel("sharp up decile (10 = sharper than stable norm)")
    _axes_sharp_signal[1, 1].set_ylabel("excess vs odds")

    _fig_sharp_signal.tight_layout()
    _fig_sharp_signal
    return


@app.cell
def _(TwoSlopeNorm, np, plt, sharp_joint_heatmap_summary):
    # セル概要: sharpness一致度×sharper度の二次元成績heatmapを描く。
    _sharp_place_matrix = (
        sharp_joint_heatmap_summary.pivot(
            index="sharp_match_bucket",
            columns="sharp_up_bucket",
            values="place_rate",
        )
        .reindex(index=range(1, 11), columns=range(1, 11))
    )
    _sharp_excess_matrix = (
        sharp_joint_heatmap_summary.pivot(
            index="sharp_match_bucket",
            columns="sharp_up_bucket",
            values="excess_place_vs_odds",
        )
        .reindex(index=range(1, 11), columns=range(1, 11))
    )

    _fig_sharp_joint, _axes_sharp_joint = plt.subplots(1, 2, figsize=(15, 6))
    _im_sharp_place = _axes_sharp_joint[0].imshow(
        _sharp_place_matrix.to_numpy(),
        aspect="auto",
        cmap="PuRd",
    )
    _axes_sharp_joint[0].set_title("Place rate by sharp match x sharp up decile")
    _axes_sharp_joint[0].set_xlabel("sharp up decile")
    _axes_sharp_joint[0].set_ylabel("sharp match decile")
    _axes_sharp_joint[0].set_xticks(range(10))
    _axes_sharp_joint[0].set_xticklabels(range(1, 11))
    _axes_sharp_joint[0].set_yticks(range(10))
    _axes_sharp_joint[0].set_yticklabels(range(1, 11))
    _fig_sharp_joint.colorbar(_im_sharp_place, ax=_axes_sharp_joint[0], fraction=0.046, pad=0.03)

    _sharp_vmin = float(np.nanmin(_sharp_excess_matrix.to_numpy()))
    _sharp_vmax = float(np.nanmax(_sharp_excess_matrix.to_numpy()))
    _sharp_norm = TwoSlopeNorm(
        vmin=min(_sharp_vmin, 0.0),
        vcenter=0.0,
        vmax=max(_sharp_vmax, 0.0),
    )
    _im_sharp_excess = _axes_sharp_joint[1].imshow(
        _sharp_excess_matrix.to_numpy(),
        aspect="auto",
        cmap="coolwarm",
        norm=_sharp_norm,
    )
    _axes_sharp_joint[1].set_title("Excess place vs odds by sharp match x sharp up decile")
    _axes_sharp_joint[1].set_xlabel("sharp up decile")
    _axes_sharp_joint[1].set_ylabel("sharp match decile")
    _axes_sharp_joint[1].set_xticks(range(10))
    _axes_sharp_joint[1].set_xticklabels(range(1, 11))
    _axes_sharp_joint[1].set_yticks(range(10))
    _axes_sharp_joint[1].set_yticklabels(range(1, 11))
    _fig_sharp_joint.colorbar(_im_sharp_excess, ax=_axes_sharp_joint[1], fraction=0.046, pad=0.03)

    _fig_sharp_joint.tight_layout()
    _fig_sharp_joint
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: sharpness二次元heatmapの読み方を補足する。
    mo.md("""
    sharpness の二次元 heatmap では、縦が「厩舎の終いパターンへの一致度」、横が「厩舎基準より終い重点か」を表します。

    - 右上が強ければ、「その厩舎らしい sharpness を保ちつつ、さらに終いが効いている馬」が走りやすいです。
    - 右だけ強ければ、厩舎型より sharper であること自体が価値を持っている可能性があります。
    - 上だけ強ければ、厩舎ごとの適正 sharpness に収まっていることの方が重要かもしれません。
    """)
    return


@app.cell
def _(sharp_match_bucket_summary, sharp_up_bucket_summary):
    # セル概要: sharpness decile集計表を確認する。
    {
        "sharp_match_bucket_summary": sharp_match_bucket_summary.round(4),
        "sharp_up_bucket_summary": sharp_up_bucket_summary.round(4),
    }
    return


@app.cell(hide_code=True)
def _(mo):
    # セル概要: 読み解き補助の見出しを表示する。
    mo.md("""
    ## 8. 読み解きメモ
    """)
    return


@app.cell
def _(mo):
    # セル概要: 可視化の読み方を簡潔に案内する。
    mo.md("""
    - `*_z_tozai_day` は同日・東西の相対比較なので、0 より小さいほどその日の中で速め、0 より大きいほど遅め。
    - `*_accel_rate` は終い加速の比率で、高いほどラストを伸ばす型。
    - `*_late_sharpness_median` は終い重点度の目安。
    - `cat1..cat9` は 4F と 1F の joint category。特定カテゴリに偏る厩舎は調教の型が安定している可能性がある。
    - `pattern_match_score` は厩舎中央値からのズレの小ささ。大きいほど「厩舎パターンに合っている」。
    - `pattern_fast_score` は厩舎中央値より相対的に速いか。大きいほど「厩舎のいつもの型より速い」。
    - `excess_place_vs_odds` は単勝オッズ帯で見た平均複勝率との差。正なら市場人気以上に走っている。
    - `sharpness_match_score` は厩舎のいつもの sharpness からどれだけズレていないか。大きいほど「sharpness パターンに合っている」。
    - `sharpness_up_score` は厩舎のいつもの sharpness より終い重点か。大きいほど「厩舎基準より sharper」。
    """)
    return


if __name__ == "__main__":
    app.run()
