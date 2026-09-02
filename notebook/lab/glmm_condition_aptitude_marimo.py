import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebookで利用する依存を読み込む。
    import json
    import re
    import sys
    from datetime import date, datetime
    from pathlib import Path

    import marimo as mo
    import pandas as pd
    from pydantic import BaseModel, Field
    from sqlalchemy import create_engine, text

    return (
        BaseModel,
        Field,
        Path,
        create_engine,
        date,
        datetime,
        json,
        mo,
        pd,
        re,
        sys,
        text,
    )


@app.cell
def _(Path, sys):
    # セル概要: プロジェクトルートとcache helperを解決する。
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
    from harp.shared.paths import notebook_analysis_cache_dir
    from pipeline.runtime_settings import load_pipeline_runtime_config

    runtime_config = load_pipeline_runtime_config()

    return (
        dataframe_cache_exists,
        load_dataframe_cache,
        notebook_analysis_cache_dir,
        project_root,
        resolve_dataframe_cache_path,
        runtime_config,
        save_dataframe_cache,
    )


@app.cell
def _(project_root):
    # セル概要: コア層の汎用GLMMランナーAPIを読み込む。
    _ = project_root
    from harp.core.modeling import (
        AptitudeRunConfig,
        SamplingStageConfig,
        build_aggregate_tables,
        default_case_presets,
        default_stage1_target_accept_by_case,
        render_report_markdown,
        run_stage_for_specs,
        select_stage2_targets,
        to_distance_bucket_4,
    )

    return (
        AptitudeRunConfig,
        SamplingStageConfig,
        build_aggregate_tables,
        default_case_presets,
        default_stage1_target_accept_by_case,
        render_report_markdown,
        run_stage_for_specs,
        select_stage2_targets,
        to_distance_bucket_4,
    )


@app.cell
def _(mo):
    # セル概要: script実行かinteractive実行かを判定する。
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(BaseModel, Field, runtime_config):
    # セル概要: notebook全体の既定設定を定義する。
    class AppConfig(BaseModel):
        db_url: str = Field(default="")
        table: str = Field(default="mart.m_train_race_horse_past5")
        start_date: str = Field(default="2023-01-01")
        race_level_min: int = Field(default=1)
        race_level_max: int = Field(default=3)
        row_limit: int = Field(default=200_000)
        use_cache_default: bool = Field(default=True)
        refresh_db_default: bool = Field(default=False)

        min_group_count: int = Field(default=100)
        min_cell_count: int = Field(default=5)
        min_condition_levels: int = Field(default=2)

        stage_mode_default: str = Field(default="stage1")
        stage1_draws: int = Field(default=300)
        stage1_tune: int = Field(default=300)
        stage1_chains: int = Field(default=2)
        stage1_cores: int = Field(default=1)

        stage2_draws: int = Field(default=1000)
        stage2_tune: int = Field(default=1000)
        stage2_chains: int = Field(default=2)
        stage2_cores: int = Field(default=1)
        stage2_p_threshold: float = Field(default=0.80)

        random_seed: int = Field(default=42)
        default_preset: str = Field(default="odds_log_z_ta097")

    cfg = AppConfig(db_url=runtime_config.database.db_url)
    return (cfg,)


@app.cell
def _(cfg, mo):
    # セル概要: UIウィジェットを作成する。
    db_url_widget = mo.ui.text(
        label="HARP_DB_URL",
        value=cfg.db_url,
        placeholder="Set HARP_DB_URL in your local .env",
        full_width=True,
    )
    table_widget = mo.ui.text(label="Table", value=cfg.table)
    start_date_widget = mo.ui.text(label="Start date", value=cfg.start_date)

    race_level_min_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_min, label="Race level min")
    race_level_max_widget = mo.ui.number(start=1, stop=10, step=1, value=cfg.race_level_max, label="Race level max")
    row_limit_widget = mo.ui.number(start=10_000, stop=2_000_000, step=10_000, value=cfg.row_limit, label="Row limit")
    use_cache_widget = mo.ui.switch(value=cfg.use_cache_default, label="Use cache")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_db_default, label="Force refresh DB")

    min_group_count_widget = mo.ui.number(start=1, step=1, value=cfg.min_group_count, label="Min group count")
    min_cell_count_widget = mo.ui.number(start=1, step=1, value=cfg.min_cell_count, label="Min cell count")
    min_condition_levels_widget = mo.ui.number(start=1, step=1, value=cfg.min_condition_levels, label="Min condition levels")

    stage_mode_widget = mo.ui.dropdown(
        options=["stage1", "stage1_stage2"],
        value=cfg.stage_mode_default,
        label="Stage mode",
    )

    stage1_draws_widget = mo.ui.number(start=20, step=20, value=cfg.stage1_draws, label="Stage1 draws")
    stage1_tune_widget = mo.ui.number(start=20, step=20, value=cfg.stage1_tune, label="Stage1 tune")
    stage1_chains_widget = mo.ui.number(start=1, stop=4, step=1, value=cfg.stage1_chains, label="Stage1 chains")
    stage1_cores_widget = mo.ui.number(start=1, stop=8, step=1, value=cfg.stage1_cores, label="Stage1 cores")

    stage2_draws_widget = mo.ui.number(start=20, step=20, value=cfg.stage2_draws, label="Stage2 draws")
    stage2_tune_widget = mo.ui.number(start=20, step=20, value=cfg.stage2_tune, label="Stage2 tune")
    stage2_chains_widget = mo.ui.number(start=1, stop=4, step=1, value=cfg.stage2_chains, label="Stage2 chains")
    stage2_cores_widget = mo.ui.number(start=1, stop=8, step=1, value=cfg.stage2_cores, label="Stage2 cores")
    stage2_threshold_widget = mo.ui.slider(
        start=0.50,
        stop=0.99,
        step=0.01,
        value=cfg.stage2_p_threshold,
        label="Stage2 p-threshold",
    )

    random_seed_widget = mo.ui.number(start=1, step=1, value=cfg.random_seed, label="Random seed")

    preset_odds_widget = mo.ui.switch(value=True, label="Preset: odds_log_z_ta097")
    preset_pos4_widget = mo.ui.switch(value=False, label="Preset: pos4_z_ta090")

    run_button = mo.ui.run_button(label="Run GLMM")

    mo.vstack(
        [
            mo.md("### DB/期間/行数"),
            db_url_widget,
            mo.hstack([table_widget, start_date_widget]),
            mo.hstack([race_level_min_widget, race_level_max_widget, row_limit_widget]),
            mo.hstack([use_cache_widget, refresh_db_widget]),
            mo.md("### 疎データしきい値"),
            mo.hstack([min_group_count_widget, min_cell_count_widget, min_condition_levels_widget]),
            mo.md("### Stage設定"),
            stage_mode_widget,
            mo.hstack([stage1_draws_widget, stage1_tune_widget, stage1_chains_widget, stage1_cores_widget]),
            mo.hstack([stage2_draws_widget, stage2_tune_widget, stage2_chains_widget, stage2_cores_widget, stage2_threshold_widget]),
            mo.md("### ケース設定"),
            mo.hstack([preset_odds_widget, preset_pos4_widget]),
            random_seed_widget,
            run_button,
        ]
    )
    return (
        db_url_widget,
        min_cell_count_widget,
        min_condition_levels_widget,
        min_group_count_widget,
        preset_odds_widget,
        preset_pos4_widget,
        race_level_max_widget,
        race_level_min_widget,
        random_seed_widget,
        refresh_db_widget,
        row_limit_widget,
        run_button,
        stage1_chains_widget,
        stage1_cores_widget,
        stage1_draws_widget,
        stage1_tune_widget,
        stage2_chains_widget,
        stage2_cores_widget,
        stage2_draws_widget,
        stage2_threshold_widget,
        stage2_tune_widget,
        stage_mode_widget,
        start_date_widget,
        table_widget,
        use_cache_widget,
    )


@app.cell
def _(
    AptitudeRunConfig,
    SamplingStageConfig,
    cfg,
    db_url_widget,
    default_case_presets,
    default_stage1_target_accept_by_case,
    is_script_mode,
    min_cell_count_widget,
    min_condition_levels_widget,
    min_group_count_widget,
    mo,
    preset_odds_widget,
    preset_pos4_widget,
    race_level_max_widget,
    race_level_min_widget,
    random_seed_widget,
    refresh_db_widget,
    row_limit_widget,
    stage1_chains_widget,
    stage1_cores_widget,
    stage1_draws_widget,
    stage1_tune_widget,
    stage2_chains_widget,
    stage2_cores_widget,
    stage2_draws_widget,
    stage2_threshold_widget,
    stage2_tune_widget,
    stage_mode_widget,
    start_date_widget,
    table_widget,
    use_cache_widget,
):
    # セル概要: script/UIの設定値を統合し、実行設定を解決する。

    def _parse_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"1", "true", "yes", "on"}:
            return True
        if s in {"0", "false", "no", "off"}:
            return False
        return default

    def _parse_int(value: object, default: int) -> int:
        if value is None:
            return default
        return int(value)

    def _parse_float(value: object, default: float) -> float:
        if value is None:
            return default
        return float(value)

    if is_script_mode:
        cli = {k.replace("-", "_"): v for k, v in mo.cli_args().items()}
        resolved_db_url = str(cli.get("db_url", cfg.db_url)).strip()
        resolved_table = str(cli.get("table", cfg.table)).strip()
        resolved_start_date = str(cli.get("start_date", cfg.start_date)).strip()
        resolved_race_level_min = _parse_int(cli.get("race_level_min"), cfg.race_level_min)
        resolved_race_level_max = _parse_int(cli.get("race_level_max"), cfg.race_level_max)
        resolved_row_limit = _parse_int(cli.get("row_limit"), cfg.row_limit)
        resolved_use_cache = _parse_bool(cli.get("use_cache"), cfg.use_cache_default)
        resolved_refresh_db = _parse_bool(cli.get("refresh_db"), cfg.refresh_db_default)

        resolved_min_group_count = _parse_int(cli.get("min_group_count"), cfg.min_group_count)
        resolved_min_cell_count = _parse_int(cli.get("min_cell_count"), cfg.min_cell_count)
        resolved_min_condition_levels = _parse_int(cli.get("min_condition_levels"), cfg.min_condition_levels)

        resolved_stage_mode = str(cli.get("stage_mode", cfg.stage_mode_default)).strip()
        resolved_stage1_draws = _parse_int(cli.get("draws", cli.get("stage1_draws")), cfg.stage1_draws)
        resolved_stage1_tune = _parse_int(cli.get("tune", cli.get("stage1_tune")), cfg.stage1_tune)
        resolved_stage1_chains = _parse_int(cli.get("chains", cli.get("stage1_chains")), cfg.stage1_chains)
        resolved_stage1_cores = _parse_int(cli.get("cores", cli.get("stage1_cores")), cfg.stage1_cores)

        resolved_stage2_draws = _parse_int(cli.get("stage2_draws"), cfg.stage2_draws)
        resolved_stage2_tune = _parse_int(cli.get("stage2_tune"), cfg.stage2_tune)
        resolved_stage2_chains = _parse_int(cli.get("stage2_chains"), cfg.stage2_chains)
        resolved_stage2_cores = _parse_int(cli.get("stage2_cores"), cfg.stage2_cores)
        resolved_stage2_threshold = _parse_float(cli.get("stage2_p_threshold"), cfg.stage2_p_threshold)

        resolved_random_seed = _parse_int(cli.get("random_seed"), cfg.random_seed)

        preset_raw = str(cli.get("preset", cfg.default_preset)).strip()
        selected_preset_ids = [p.strip() for p in preset_raw.split(",") if p.strip()]
    else:
        resolved_db_url = str(db_url_widget.value).strip()
        resolved_table = str(table_widget.value).strip()
        resolved_start_date = str(start_date_widget.value).strip()
        resolved_race_level_min = int(race_level_min_widget.value)
        resolved_race_level_max = int(race_level_max_widget.value)
        resolved_row_limit = int(row_limit_widget.value)
        resolved_use_cache = bool(use_cache_widget.value)
        resolved_refresh_db = bool(refresh_db_widget.value)

        resolved_min_group_count = int(min_group_count_widget.value)
        resolved_min_cell_count = int(min_cell_count_widget.value)
        resolved_min_condition_levels = int(min_condition_levels_widget.value)

        resolved_stage_mode = str(stage_mode_widget.value).strip()
        resolved_stage1_draws = int(stage1_draws_widget.value)
        resolved_stage1_tune = int(stage1_tune_widget.value)
        resolved_stage1_chains = int(stage1_chains_widget.value)
        resolved_stage1_cores = int(stage1_cores_widget.value)

        resolved_stage2_draws = int(stage2_draws_widget.value)
        resolved_stage2_tune = int(stage2_tune_widget.value)
        resolved_stage2_chains = int(stage2_chains_widget.value)
        resolved_stage2_cores = int(stage2_cores_widget.value)
        resolved_stage2_threshold = float(stage2_threshold_widget.value)

        resolved_random_seed = int(random_seed_widget.value)

        selected_preset_ids = []
        if bool(preset_odds_widget.value):
            selected_preset_ids.append("odds_log_z_ta097")
        if bool(preset_pos4_widget.value):
            selected_preset_ids.append("pos4_z_ta090")

    if not resolved_db_url:
        raise ValueError("HARP_DB_URL is required.")
    if resolved_race_level_min > resolved_race_level_max:
        raise ValueError("race_level_min must be <= race_level_max")
    if resolved_row_limit <= 0:
        raise ValueError("row_limit must be positive")
    if resolved_stage_mode not in {"stage1", "stage1_stage2"}:
        raise ValueError(f"Invalid stage_mode: {resolved_stage_mode}")

    presets = default_case_presets()
    if not selected_preset_ids:
        raise ValueError("At least one preset must be selected.")

    unknown = [p for p in selected_preset_ids if p not in presets]
    if unknown:
        raise ValueError(f"Unknown preset(s): {unknown}")

    selected_cases = [presets[p] for p in selected_preset_ids]
    stage1_target_accept_map = default_stage1_target_accept_by_case()

    stage1_cfg_by_case = {
        case.case_id: SamplingStageConfig(
            draws=resolved_stage1_draws,
            tune=resolved_stage1_tune,
            chains=resolved_stage1_chains,
            cores=resolved_stage1_cores,
            target_accept=float(stage1_target_accept_map.get(case.case_id, 0.90)),
        )
        for case in selected_cases
    }
    stage2_cfg_by_case = {
        case.case_id: SamplingStageConfig(
            draws=resolved_stage2_draws,
            tune=resolved_stage2_tune,
            chains=resolved_stage2_chains,
            cores=resolved_stage2_cores,
            target_accept=0.95,
        )
        for case in selected_cases
    }

    run_cfg = AptitudeRunConfig(
        table=resolved_table,
        start_date=resolved_start_date,
        race_level_min=resolved_race_level_min,
        race_level_max=resolved_race_level_max,
        row_limit=resolved_row_limit,
        min_group_count=resolved_min_group_count,
        min_cell_count=resolved_min_cell_count,
        min_condition_levels=resolved_min_condition_levels,
        stage_mode=resolved_stage_mode,
    )
    return (
        resolved_db_url,
        resolved_random_seed,
        resolved_refresh_db,
        resolved_stage2_threshold,
        resolved_use_cache,
        run_cfg,
        selected_cases,
        stage1_cfg_by_case,
        stage2_cfg_by_case,
    )


@app.cell
def _(date, project_root):
    # セル概要: 出力先パスを準備する。
    today = date.today().strftime("%Y%m%d")
    output_root = project_root / "notebook" / "lab" / "tmp" / "group_condition_glmm_runs"
    report_results_dir = project_root / "notebook" / "report" / "results"
    report_features_dir = project_root / "notebook" / "report" / "features"
    logs_dir = project_root / "outputs" / f"glmm_condition_aptitude_marimo_logs_{today}"

    output_root.mkdir(parents=True, exist_ok=True)
    report_results_dir.mkdir(parents=True, exist_ok=True)
    report_features_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    aggregate_runs_path = report_results_dir / f"{today}_glmm_condition_aptitude_marimo_runs.csv"
    aggregate_compare_path = report_results_dir / f"{today}_glmm_condition_aptitude_marimo_compare.csv"
    report_path = report_features_dir / f"{today}_glmm_condition_aptitude_marimo_report.md"
    return (
        aggregate_compare_path,
        aggregate_runs_path,
        logs_dir,
        output_root,
        report_path,
    )


@app.cell
def _(
    create_engine,
    pd,
    notebook_analysis_cache_dir,
    project_root,
    re,
    resolved_db_url,
    resolved_refresh_db,
    resolved_use_cache,
    run_cfg,
    selected_cases,
    text,
):
    # セル概要: DBから必要列を読み込み、キャッシュを利用してデータを解決する。
    ability_cols = sorted({case.ability_col for case in selected_cases})
    needed_cols = [
        "race_id",
        "held_date",
        "race_level",
        "is_place",
        "jockey_cd",
        "sire_id",
        "distance_m",
        "jyo_cd",
        "course_cluster",
        *ability_cols,
    ]

    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    ability_part = "_".join(ability_cols)
    stem = (
        f"glmm_marimo_{run_cfg.table.replace('.', '_')}_{ability_part}_"
        f"{run_cfg.start_date}_{run_cfg.race_level_min}_{run_cfg.race_level_max}_{run_cfg.row_limit}"
    )
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)
    cache_path = cache_dir / f"{safe_stem}.parquet"

    use_cache = (
        resolved_use_cache
        and dataframe_cache_exists(cache_path)
        and (not resolved_refresh_db)
    )
    if use_cache:
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading: {cache_source_path}")
        df = load_dataframe_cache(cache_path)
    else:
        engine = create_engine(resolved_db_url)
        sql = text(
            f"""
            SELECT {", ".join(needed_cols)}
            FROM {run_cfg.table}
            WHERE held_date >= :start_date
              AND race_level BETWEEN :race_level_min AND :race_level_max
            ORDER BY held_date, race_id
            LIMIT :row_limit
            """
        )
        with engine.connect().execution_options(stream_results=True) as conn:
            df = pd.read_sql_query(
                sql,
                conn,
                params={
                    "start_date": run_cfg.start_date,
                    "race_level_min": run_cfg.race_level_min,
                    "race_level_max": run_cfg.race_level_max,
                    "row_limit": run_cfg.row_limit,
                },
            )
        if resolved_use_cache:
            save_dataframe_cache(df, cache_path)
            print(f"[cache] saved: {cache_path}")

    if df.empty:
        raise ValueError("Query returned 0 rows.")
    return (df,)


@app.cell
def _(df, mo, selected_cases, to_distance_bucket_4):
    # セル概要: 共通条件列を追加し、入力データを確認する。
    df_work = df.copy()
    df_work["distance_bucket_4"] = to_distance_bucket_4(df_work["distance_m"])

    mo.vstack(
        [
            mo.md(f"Rows: `{len(df_work):,}`"),
            mo.md(f"Cases: `{', '.join(case.case_id for case in selected_cases)}`"),
            df_work.head(8),
        ]
    )
    return (df_work,)


@app.cell
def _(is_script_mode, run_button):
    # セル概要: scriptでは自動実行、interactiveではボタンクリックで実行する。
    should_run = is_script_mode or bool(run_button.value)
    return (should_run,)


@app.cell
def _(
    aggregate_compare_path,
    aggregate_runs_path,
    build_aggregate_tables,
    datetime,
    df_work,
    json,
    logs_dir,
    output_root,
    render_report_markdown,
    report_path,
    resolved_random_seed,
    resolved_stage2_threshold,
    run_cfg,
    run_stage_for_specs,
    select_stage2_targets,
    selected_cases,
    should_run,
    stage1_cfg_by_case,
    stage2_cfg_by_case,
):
    # セル概要: ケースを順に実行し、集約結果と成果物を保存する。
    compare_df = None
    results_df = None
    run_summary = {
        "status": "idle",
        "message": "Press `Run GLMM` to start.",
    }

    if should_run:
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_root = output_root / session_ts
        session_root.mkdir(parents=True, exist_ok=True)

        all_results = []
        stage2_targets_by_case: dict[str, list[str]] = {}

        for case in selected_cases:
            case_dir = session_root / case.case_id
            case_dir.mkdir(parents=True, exist_ok=True)

            stage1_cfg = stage1_cfg_by_case[case.case_id]
            stage1_results, stage1_artifacts = run_stage_for_specs(
                df_work,
                run_cfg,
                case,
                stage1_cfg,
                stage="stage1",
                random_seed=resolved_random_seed,
            )
            all_results.extend(stage1_results)

            for r in stage1_results:
                run_name = f"{r.stage}_{r.model_id}"
                art = stage1_artifacts[r.model_id]
                summary_path = case_dir / f"{run_name}_summary.csv"
                ranking_path = case_dir / f"{run_name}_group_condition_ranking.csv"
                config_path = case_dir / f"{run_name}_config.json"

                art["summary_df"].to_csv(summary_path, index=True)
                art["ranking_df"].to_csv(ranking_path, index=False)
                config_path.write_text(json.dumps(art["config"], ensure_ascii=False, indent=2), encoding="utf-8")

                log_payload = {
                    "run_name": run_name,
                    "case_id": case.case_id,
                    "status": r.status,
                    "error_message": r.error_message,
                    "model_id": r.model_id,
                    "stage": r.stage,
                    "sigma_gc_mean": r.sigma_gc_mean,
                    "sigma_gc_hdi_low": r.sigma_gc_hdi_low,
                    "sigma_gc_hdi_high": r.sigma_gc_hdi_high,
                    "p_sigma_gc_gt_rope": r.p_sigma_gc_gt_rope,
                    "global_aptitude_flag": r.global_aptitude_flag,
                    "local_aptitude_count": r.local_aptitude_count,
                    "summary_path": str(summary_path),
                    "ranking_path": str(ranking_path),
                    "config_path": str(config_path),
                }
                (logs_dir / f"{case.case_id}_{run_name}.json").write_text(
                    json.dumps(log_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            if run_cfg.stage_mode == "stage1_stage2":
                stage2_targets = select_stage2_targets(stage1_results, threshold=resolved_stage2_threshold)
                stage2_targets_by_case[case.case_id] = stage2_targets
                if stage2_targets:
                    target_set = set(stage2_targets)
                    stage2_case = case.__class__(
                        case_id=case.case_id,
                        ability_col=case.ability_col,
                        ability_transform=case.ability_transform,
                        rope=case.rope,
                        group_condition_specs=tuple(
                            spec for spec in case.group_condition_specs if spec.model_id in target_set
                        ),
                    )
                    stage2_cfg = stage2_cfg_by_case[case.case_id]
                    stage2_results, stage2_artifacts = run_stage_for_specs(
                        df_work,
                        run_cfg,
                        stage2_case,
                        stage2_cfg,
                        stage="stage2",
                        random_seed=resolved_random_seed + 100,
                    )
                    all_results.extend(stage2_results)

                    for r in stage2_results:
                        run_name = f"{r.stage}_{r.model_id}"
                        art = stage2_artifacts[r.model_id]
                        summary_path = case_dir / f"{run_name}_summary.csv"
                        ranking_path = case_dir / f"{run_name}_group_condition_ranking.csv"
                        config_path = case_dir / f"{run_name}_config.json"

                        art["summary_df"].to_csv(summary_path, index=True)
                        art["ranking_df"].to_csv(ranking_path, index=False)
                        config_path.write_text(json.dumps(art["config"], ensure_ascii=False, indent=2), encoding="utf-8")

                        log_payload = {
                            "run_name": run_name,
                            "case_id": case.case_id,
                            "status": r.status,
                            "error_message": r.error_message,
                            "model_id": r.model_id,
                            "stage": r.stage,
                            "sigma_gc_mean": r.sigma_gc_mean,
                            "sigma_gc_hdi_low": r.sigma_gc_hdi_low,
                            "sigma_gc_hdi_high": r.sigma_gc_hdi_high,
                            "p_sigma_gc_gt_rope": r.p_sigma_gc_gt_rope,
                            "global_aptitude_flag": r.global_aptitude_flag,
                            "local_aptitude_count": r.local_aptitude_count,
                            "summary_path": str(summary_path),
                            "ranking_path": str(ranking_path),
                            "config_path": str(config_path),
                        }
                        (logs_dir / f"{case.case_id}_{run_name}.json").write_text(
                            json.dumps(log_payload, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )

        results_df, compare_df = build_aggregate_tables(all_results)
        results_df.to_csv(aggregate_runs_path, index=False)
        compare_df.to_csv(aggregate_compare_path, index=False)

        report_text = render_report_markdown(
            run_cfg=run_cfg,
            case_configs=selected_cases,
            stage1_cfg_by_case=stage1_cfg_by_case,
            stage2_cfg_by_case=stage2_cfg_by_case,
            results_df=results_df,
            compare_df=compare_df,
            stage2_targets_by_case=stage2_targets_by_case if stage2_targets_by_case else None,
            created_at=datetime.now().isoformat(timespec="seconds"),
            title="GLMM条件別適性検証レポート（marimo汎用基盤）",
        )
        report_path.write_text(report_text, encoding="utf-8")

        run_summary = {
            "status": "completed",
            "session_root": str(session_root),
            "aggregate_runs_path": str(aggregate_runs_path),
            "aggregate_compare_path": str(aggregate_compare_path),
            "report_path": str(report_path),
            "cases": [case.case_id for case in selected_cases],
        }
    return compare_df, results_df, run_summary


@app.cell
def _(compare_df, mo, results_df, run_summary):
    # セル概要: 実行サマリと集約結果を表示する。
    if run_summary is None:
        display = mo.md("No run summary.")
    elif run_summary.get("status") == "idle":
        display = mo.md(str(run_summary.get("message", "idle")))
    else:
        display = mo.vstack(
            [
                mo.md("## 2. 実行結果"),
                mo.md(f"Session: `{run_summary['session_root']}`"),
                mo.md(f"Runs CSV: `{run_summary['aggregate_runs_path']}`"),
                mo.md(f"Compare CSV: `{run_summary['aggregate_compare_path']}`"),
                mo.md(f"Report: `{run_summary['report_path']}`"),
                mo.md("### results_df"),
                results_df,
                mo.md("### compare_df"),
                compare_df,
            ]
        )
    display
    return


if __name__ == "__main__":
    app.run()
