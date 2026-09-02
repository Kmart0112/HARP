import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium")


@app.cell
def _():
    # セル概要: notebookで利用する依存を読み込む。
    import hashlib
    import io
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
        hashlib,
        io,
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
        AptitudeCaseConfig,
        AptitudeRunConfig,
        GroupConditionSpec,
        SamplingStageConfig,
        build_aggregate_tables,
        render_report_markdown,
        run_stage_for_specs,
        select_stage2_targets,
    )

    return (
        AptitudeCaseConfig,
        AptitudeRunConfig,
        GroupConditionSpec,
        SamplingStageConfig,
        build_aggregate_tables,
        render_report_markdown,
        run_stage_for_specs,
        select_stage2_targets,
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

        outcome_col: str = Field(default="is_place")
        ability_col: str = Field(default="odds_tansho")
        ability_transform: str = Field(default="log_z")
        rope: float = Field(default=0.05)

        min_group_count: int = Field(default=100)
        min_cell_count: int = Field(default=5)
        min_condition_levels: int = Field(default=2)

        stage_mode_default: str = Field(default="stage1")
        stage1_draws: int = Field(default=300)
        stage1_tune: int = Field(default=300)
        stage1_chains: int = Field(default=2)
        stage1_cores: int = Field(default=1)
        stage1_target_accept: float = Field(default=0.90)

        stage2_draws: int = Field(default=1000)
        stage2_tune: int = Field(default=1000)
        stage2_chains: int = Field(default=2)
        stage2_cores: int = Field(default=1)
        stage2_target_accept: float = Field(default=0.95)
        stage2_p_threshold: float = Field(default=0.80)

        random_seed: int = Field(default=42)
        specs_csv_default: str = Field(
            default=(
                "model_id,group_col,condition_col\n"
                "demo_jockey_distance,jockey_cd,distance_m\n"
                "demo_sire_course,sire_id,course_cluster\n"
            )
        )

    cfg = AppConfig(db_url=runtime_config.database.db_url)
    return (cfg,)


@app.cell
def _(hashlib, io, json, notebook_analysis_cache_dir, pd, re):
    # セル概要: specs解析や出力保存に使う小さなhelperを定義する。
    identifier_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    table_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?")

    def parse_bool(value: object, default: bool) -> bool:
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

    def parse_int(value: object, default: int) -> int:
        if value is None:
            return default
        return int(value)

    def parse_float(value: object, default: float) -> float:
        if value is None:
            return default
        return float(value)

    def validate_identifier(value: str, field_name: str) -> str:
        candidate = str(value).strip()
        if not candidate:
            raise ValueError(f"{field_name} must not be empty.")
        if not identifier_re.fullmatch(candidate):
            raise ValueError(f"Invalid SQL identifier for {field_name}: {candidate}")
        return candidate

    def validate_table_name(table_name: str) -> str:
        candidate = str(table_name).strip()
        if not table_re.fullmatch(candidate):
            raise ValueError(f"Invalid table name: {candidate}")
        return candidate

    def parse_specs_csv(raw: str) -> pd.DataFrame:
        text_value = str(raw).strip()
        if not text_value:
            raise ValueError("specs_csv must not be empty.")
        try:
            df = pd.read_csv(io.StringIO(text_value), dtype="string")
        except Exception as exc:
            raise ValueError(f"Failed to parse specs CSV: {exc}") from exc

        required = ["model_id", "group_col", "condition_col"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"specs_csv is missing required columns: {missing}")

        specs_df = df.loc[:, required].copy()
        for col in required:
            specs_df[col] = specs_df[col].fillna("").astype("string").str.strip()

        blank_mask = (specs_df == "").all(axis=1)
        specs_df = specs_df.loc[~blank_mask].reset_index(drop=True)
        if specs_df.empty:
            raise ValueError("specs_csv must contain at least one non-empty spec row.")

        invalid_rows = specs_df.index[
            (specs_df["model_id"] == "")
            | (specs_df["group_col"] == "")
            | (specs_df["condition_col"] == "")
        ].tolist()
        if invalid_rows:
            raise ValueError(
                f"specs_csv contains empty required fields at rows: {[idx + 2 for idx in invalid_rows]}"
            )

        duplicate_model_ids = specs_df["model_id"][specs_df["model_id"].duplicated()].tolist()
        if duplicate_model_ids:
            raise ValueError(f"specs_csv contains duplicate model_id values: {duplicate_model_ids}")

        specs_df["model_id"] = specs_df["model_id"].astype(str)
        specs_df["group_col"] = specs_df["group_col"].map(
            lambda value: validate_identifier(value, "group_col")
        )
        specs_df["condition_col"] = specs_df["condition_col"].map(
            lambda value: validate_identifier(value, "condition_col")
        )
        return specs_df

    def build_required_columns(
        *,
        outcome_col: str,
        ability_col: str,
        specs_df: pd.DataFrame,
    ) -> list[str]:
        columns = ["race_id", "held_date", "race_level", outcome_col, ability_col]
        columns.extend(specs_df["group_col"].tolist())
        columns.extend(specs_df["condition_col"].tolist())

        ordered_unique: list[str] = []
        seen: set[str] = set()
        for col in columns:
            if col not in seen:
                seen.add(col)
                ordered_unique.append(col)
        return ordered_unique

    def build_cache_path(
        *,
        project_root,
        run_cfg,
        outcome_col: str,
        ability_col: str,
        ability_transform: str,
        specs_df: pd.DataFrame,
    ):
        _ = project_root
        cache_dir = notebook_analysis_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        spec_signature = hashlib.sha1(
            specs_df.to_csv(index=False).encode("utf-8")
        ).hexdigest()[:12]
        stem = (
            f"glmm_generic_marimo_{run_cfg.table.replace('.', '_')}_"
            f"{outcome_col}_{ability_col}_{ability_transform}_"
            f"{run_cfg.start_date}_{run_cfg.race_level_min}_{run_cfg.race_level_max}_{run_cfg.row_limit}_"
            f"{spec_signature}"
        )
        safe_stem = re.sub(r"[^A-Za-z0-9_\\-]", "_", stem)
        return cache_dir / f"{safe_stem}.parquet"

    def build_case_id(*, ability_col: str, ability_transform: str) -> str:
        raw = f"generic_{ability_col}_{ability_transform}"
        return re.sub(r"[^A-Za-z0-9_\\-]", "_", raw).strip("_") or "generic_case"

    def safe_file_stem(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_\\-]", "_", str(value).strip())
        return safe or "run"

    def save_stage_artifacts(
        *,
        case_dir,
        case_cfg,
        logs_dir,
        results,
        artifacts: dict[str, dict[str, object]],
    ) -> dict[tuple[str, str], dict[str, str]]:
        path_map: dict[tuple[str, str], dict[str, str]] = {}
        for res in results:
            artifact = artifacts.get(res.model_id, {})
            run_name = f"{res.stage}_{safe_file_stem(res.model_id)}"
            summary_path = case_dir / f"{run_name}_summary.csv"
            ranking_path = case_dir / f"{run_name}_group_condition_ranking.csv"
            config_path = case_dir / f"{run_name}_config.json"

            summary_df = artifact.get("summary_df", pd.DataFrame())
            ranking_df = artifact.get("ranking_df", pd.DataFrame())
            config_dict = artifact.get("config", {})

            if isinstance(summary_df, pd.DataFrame):
                summary_df.to_csv(summary_path, index=True)
            if isinstance(ranking_df, pd.DataFrame):
                ranking_df.to_csv(ranking_path, index=False)
            config_path.write_text(
                json.dumps(config_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            log_payload = {
                "run_name": run_name,
                "case_id": case_cfg.case_id,
                "status": res.status,
                "error_message": res.error_message,
                "model_id": res.model_id,
                "group_col": res.group_col,
                "condition_col": res.condition_col,
                "stage": res.stage,
                "sigma_gc_mean": res.sigma_gc_mean,
                "sigma_gc_hdi_low": res.sigma_gc_hdi_low,
                "sigma_gc_hdi_high": res.sigma_gc_hdi_high,
                "p_sigma_gc_gt_rope": res.p_sigma_gc_gt_rope,
                "global_aptitude_flag": res.global_aptitude_flag,
                "local_aptitude_count": res.local_aptitude_count,
                "summary_path": str(summary_path),
                "ranking_path": str(ranking_path),
                "config_path": str(config_path),
                "runner_error": artifact.get("error"),
            }
            (logs_dir / f"{case_cfg.case_id}_{run_name}.json").write_text(
                json.dumps(log_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            path_map[(res.stage, res.model_id)] = {
                "summary_path": str(summary_path),
                "ranking_path": str(ranking_path),
                "config_path": str(config_path),
            }
        return path_map

    return (
        build_cache_path,
        build_case_id,
        build_required_columns,
        parse_bool,
        parse_float,
        parse_int,
        parse_specs_csv,
        safe_file_stem,
        save_stage_artifacts,
        validate_identifier,
        validate_table_name,
    )


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

    race_level_min_widget = mo.ui.number(
        start=1,
        stop=10,
        step=1,
        value=cfg.race_level_min,
        label="Race level min",
    )
    race_level_max_widget = mo.ui.number(
        start=1,
        stop=10,
        step=1,
        value=cfg.race_level_max,
        label="Race level max",
    )
    row_limit_widget = mo.ui.number(
        start=10_000,
        stop=2_000_000,
        step=10_000,
        value=cfg.row_limit,
        label="Row limit",
    )
    use_cache_widget = mo.ui.switch(value=cfg.use_cache_default, label="Use cache")
    refresh_db_widget = mo.ui.switch(value=cfg.refresh_db_default, label="Force refresh DB")

    outcome_col_widget = mo.ui.text(label="Outcome col", value=cfg.outcome_col)
    ability_col_widget = mo.ui.text(label="Ability col", value=cfg.ability_col)
    ability_transform_widget = mo.ui.dropdown(
        options=["none", "log", "z", "log_z"],
        value=cfg.ability_transform,
        label="Ability transform",
    )
    rope_widget = mo.ui.number(start=0.01, step=0.01, value=cfg.rope, label="ROPE")

    min_group_count_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.min_group_count,
        label="Min group count",
    )
    min_cell_count_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.min_cell_count,
        label="Min cell count",
    )
    min_condition_levels_widget = mo.ui.number(
        start=1,
        step=1,
        value=cfg.min_condition_levels,
        label="Min condition levels",
    )

    stage_mode_widget = mo.ui.dropdown(
        options=["stage1", "stage1_stage2"],
        value=cfg.stage_mode_default,
        label="Stage mode",
    )
    stage1_draws_widget = mo.ui.number(
        start=20,
        step=20,
        value=cfg.stage1_draws,
        label="Stage1 draws",
    )
    stage1_tune_widget = mo.ui.number(
        start=20,
        step=20,
        value=cfg.stage1_tune,
        label="Stage1 tune",
    )
    stage1_chains_widget = mo.ui.number(
        start=1,
        stop=4,
        step=1,
        value=cfg.stage1_chains,
        label="Stage1 chains",
    )
    stage1_cores_widget = mo.ui.number(
        start=1,
        stop=8,
        step=1,
        value=cfg.stage1_cores,
        label="Stage1 cores",
    )
    stage1_target_accept_widget = mo.ui.slider(
        start=0.80,
        stop=0.99,
        step=0.01,
        value=cfg.stage1_target_accept,
        label="Stage1 target_accept",
    )

    stage2_draws_widget = mo.ui.number(
        start=20,
        step=20,
        value=cfg.stage2_draws,
        label="Stage2 draws",
    )
    stage2_tune_widget = mo.ui.number(
        start=20,
        step=20,
        value=cfg.stage2_tune,
        label="Stage2 tune",
    )
    stage2_chains_widget = mo.ui.number(
        start=1,
        stop=4,
        step=1,
        value=cfg.stage2_chains,
        label="Stage2 chains",
    )
    stage2_cores_widget = mo.ui.number(
        start=1,
        stop=8,
        step=1,
        value=cfg.stage2_cores,
        label="Stage2 cores",
    )
    stage2_target_accept_widget = mo.ui.slider(
        start=0.80,
        stop=0.99,
        step=0.01,
        value=cfg.stage2_target_accept,
        label="Stage2 target_accept",
    )
    stage2_threshold_widget = mo.ui.slider(
        start=0.50,
        stop=0.99,
        step=0.01,
        value=cfg.stage2_p_threshold,
        label="Stage2 p-threshold",
    )

    random_seed_widget = mo.ui.number(start=1, step=1, value=cfg.random_seed, label="Random seed")
    specs_csv_widget = mo.ui.text_area(
        value=cfg.specs_csv_default,
        label="Specs CSV",
        full_width=True,
    )
    run_button = mo.ui.run_button(label="Run GLMM")

    mo.vstack(
        [
            mo.md("### DB/期間/行数"),
            db_url_widget,
            mo.hstack([table_widget, start_date_widget]),
            mo.hstack([race_level_min_widget, race_level_max_widget, row_limit_widget]),
            mo.hstack([use_cache_widget, refresh_db_widget]),
            mo.md("### 実行対象"),
            mo.hstack([outcome_col_widget, ability_col_widget, ability_transform_widget, rope_widget]),
            mo.md("### 疎データしきい値"),
            mo.hstack([min_group_count_widget, min_cell_count_widget, min_condition_levels_widget]),
            mo.md("### Stage設定"),
            stage_mode_widget,
            mo.hstack(
                [
                    stage1_draws_widget,
                    stage1_tune_widget,
                    stage1_chains_widget,
                    stage1_cores_widget,
                    stage1_target_accept_widget,
                ]
            ),
            mo.hstack(
                [
                    stage2_draws_widget,
                    stage2_tune_widget,
                    stage2_chains_widget,
                    stage2_cores_widget,
                    stage2_target_accept_widget,
                    stage2_threshold_widget,
                ]
            ),
            random_seed_widget,
            mo.md("### Spec定義"),
            mo.md("`model_id,group_col,condition_col` の header 必須 CSV を入力します。"),
            specs_csv_widget,
            run_button,
        ]
    )
    return (
        ability_col_widget,
        ability_transform_widget,
        db_url_widget,
        min_cell_count_widget,
        min_condition_levels_widget,
        min_group_count_widget,
        outcome_col_widget,
        race_level_max_widget,
        race_level_min_widget,
        random_seed_widget,
        refresh_db_widget,
        rope_widget,
        row_limit_widget,
        run_button,
        specs_csv_widget,
        stage1_chains_widget,
        stage1_cores_widget,
        stage1_draws_widget,
        stage1_target_accept_widget,
        stage1_tune_widget,
        stage2_chains_widget,
        stage2_cores_widget,
        stage2_draws_widget,
        stage2_target_accept_widget,
        stage2_threshold_widget,
        stage2_tune_widget,
        stage_mode_widget,
        start_date_widget,
        table_widget,
        use_cache_widget,
    )


@app.cell
def _(
    AptitudeCaseConfig,
    AptitudeRunConfig,
    GroupConditionSpec,
    SamplingStageConfig,
    build_case_id,
    parse_bool,
    parse_float,
    parse_int,
    parse_specs_csv,
    validate_identifier,
    validate_table_name,
    ability_col_widget,
    ability_transform_widget,
    cfg,
    db_url_widget,
    is_script_mode,
    min_cell_count_widget,
    min_condition_levels_widget,
    min_group_count_widget,
    mo,
    outcome_col_widget,
    race_level_max_widget,
    race_level_min_widget,
    random_seed_widget,
    refresh_db_widget,
    rope_widget,
    row_limit_widget,
    specs_csv_widget,
    stage1_chains_widget,
    stage1_cores_widget,
    stage1_draws_widget,
    stage1_target_accept_widget,
    stage1_tune_widget,
    stage2_chains_widget,
    stage2_cores_widget,
    stage2_draws_widget,
    stage2_target_accept_widget,
    stage2_threshold_widget,
    stage2_tune_widget,
    stage_mode_widget,
    start_date_widget,
    table_widget,
    use_cache_widget,
):
    # セル概要: script/UIの設定値を統合し、実行設定とspecを解決する。
    if is_script_mode:
        cli = {k.replace("-", "_"): v for k, v in mo.cli_args().items()}
        resolved_db_url = str(cli.get("db_url", cfg.db_url)).strip()
        resolved_table = validate_table_name(str(cli.get("table", cfg.table)).strip())
        resolved_start_date = str(cli.get("start_date", cfg.start_date)).strip()
        resolved_race_level_min = parse_int(cli.get("race_level_min"), cfg.race_level_min)
        resolved_race_level_max = parse_int(cli.get("race_level_max"), cfg.race_level_max)
        resolved_row_limit = parse_int(cli.get("row_limit"), cfg.row_limit)
        resolved_use_cache = parse_bool(cli.get("use_cache"), cfg.use_cache_default)
        resolved_refresh_db = parse_bool(cli.get("refresh_db"), cfg.refresh_db_default)

        resolved_outcome_col = validate_identifier(
            str(cli.get("outcome_col", cfg.outcome_col)).strip(),
            "outcome_col",
        )
        resolved_ability_col = validate_identifier(
            str(cli.get("ability_col", cfg.ability_col)).strip(),
            "ability_col",
        )
        resolved_ability_transform = str(
            cli.get("ability_transform", cfg.ability_transform)
        ).strip()
        resolved_rope = parse_float(cli.get("rope"), cfg.rope)

        resolved_min_group_count = parse_int(cli.get("min_group_count"), cfg.min_group_count)
        resolved_min_cell_count = parse_int(cli.get("min_cell_count"), cfg.min_cell_count)
        resolved_min_condition_levels = parse_int(
            cli.get("min_condition_levels"),
            cfg.min_condition_levels,
        )

        resolved_stage_mode = str(cli.get("stage_mode", cfg.stage_mode_default)).strip()
        resolved_stage1_draws = parse_int(cli.get("draws", cli.get("stage1_draws")), cfg.stage1_draws)
        resolved_stage1_tune = parse_int(cli.get("tune", cli.get("stage1_tune")), cfg.stage1_tune)
        resolved_stage1_chains = parse_int(
            cli.get("chains", cli.get("stage1_chains")),
            cfg.stage1_chains,
        )
        resolved_stage1_cores = parse_int(
            cli.get("cores", cli.get("stage1_cores")),
            cfg.stage1_cores,
        )
        resolved_stage1_target_accept = parse_float(
            cli.get("target_accept", cli.get("stage1_target_accept")),
            cfg.stage1_target_accept,
        )

        resolved_stage2_draws = parse_int(cli.get("stage2_draws"), cfg.stage2_draws)
        resolved_stage2_tune = parse_int(cli.get("stage2_tune"), cfg.stage2_tune)
        resolved_stage2_chains = parse_int(cli.get("stage2_chains"), cfg.stage2_chains)
        resolved_stage2_cores = parse_int(cli.get("stage2_cores"), cfg.stage2_cores)
        resolved_stage2_target_accept = parse_float(
            cli.get("stage2_target_accept"),
            cfg.stage2_target_accept,
        )
        resolved_stage2_threshold = parse_float(
            cli.get("stage2_p_threshold"),
            cfg.stage2_p_threshold,
        )
        resolved_random_seed = parse_int(cli.get("random_seed"), cfg.random_seed)
        resolved_specs_csv = str(cli.get("specs_csv", cfg.specs_csv_default))
    else:
        resolved_db_url = str(db_url_widget.value).strip()
        resolved_table = validate_table_name(str(table_widget.value).strip())
        resolved_start_date = str(start_date_widget.value).strip()
        resolved_race_level_min = int(race_level_min_widget.value)
        resolved_race_level_max = int(race_level_max_widget.value)
        resolved_row_limit = int(row_limit_widget.value)
        resolved_use_cache = bool(use_cache_widget.value)
        resolved_refresh_db = bool(refresh_db_widget.value)

        resolved_outcome_col = validate_identifier(str(outcome_col_widget.value).strip(), "outcome_col")
        resolved_ability_col = validate_identifier(str(ability_col_widget.value).strip(), "ability_col")
        resolved_ability_transform = str(ability_transform_widget.value).strip()
        resolved_rope = float(rope_widget.value)

        resolved_min_group_count = int(min_group_count_widget.value)
        resolved_min_cell_count = int(min_cell_count_widget.value)
        resolved_min_condition_levels = int(min_condition_levels_widget.value)

        resolved_stage_mode = str(stage_mode_widget.value).strip()
        resolved_stage1_draws = int(stage1_draws_widget.value)
        resolved_stage1_tune = int(stage1_tune_widget.value)
        resolved_stage1_chains = int(stage1_chains_widget.value)
        resolved_stage1_cores = int(stage1_cores_widget.value)
        resolved_stage1_target_accept = float(stage1_target_accept_widget.value)

        resolved_stage2_draws = int(stage2_draws_widget.value)
        resolved_stage2_tune = int(stage2_tune_widget.value)
        resolved_stage2_chains = int(stage2_chains_widget.value)
        resolved_stage2_cores = int(stage2_cores_widget.value)
        resolved_stage2_target_accept = float(stage2_target_accept_widget.value)
        resolved_stage2_threshold = float(stage2_threshold_widget.value)
        resolved_random_seed = int(random_seed_widget.value)
        resolved_specs_csv = str(specs_csv_widget.value)

    if not resolved_db_url:
        raise ValueError("HARP_DB_URL is required.")
    if resolved_race_level_min > resolved_race_level_max:
        raise ValueError("race_level_min must be <= race_level_max")
    if resolved_row_limit <= 0:
        raise ValueError("row_limit must be positive")
    if resolved_rope <= 0.0:
        raise ValueError("rope must be > 0")
    if resolved_stage_mode not in {"stage1", "stage1_stage2"}:
        raise ValueError(f"Invalid stage_mode: {resolved_stage_mode}")
    if resolved_ability_transform not in {"none", "log", "z", "log_z"}:
        raise ValueError(f"Invalid ability_transform: {resolved_ability_transform}")

    specs_df = parse_specs_csv(resolved_specs_csv)
    group_condition_specs = tuple(
        GroupConditionSpec(
            model_id=row["model_id"],
            group_col=row["group_col"],
            condition_col=row["condition_col"],
        )
        for _, row in specs_df.iterrows()
    )
    case_cfg = AptitudeCaseConfig(
        case_id=build_case_id(
            ability_col=resolved_ability_col,
            ability_transform=resolved_ability_transform,
        ),
        ability_col=resolved_ability_col,
        ability_transform=resolved_ability_transform,
        rope=resolved_rope,
        group_condition_specs=group_condition_specs,
    )
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
    stage1_cfg = SamplingStageConfig(
        draws=resolved_stage1_draws,
        tune=resolved_stage1_tune,
        chains=resolved_stage1_chains,
        cores=resolved_stage1_cores,
        target_accept=resolved_stage1_target_accept,
    )
    stage2_cfg = SamplingStageConfig(
        draws=resolved_stage2_draws,
        tune=resolved_stage2_tune,
        chains=resolved_stage2_chains,
        cores=resolved_stage2_cores,
        target_accept=resolved_stage2_target_accept,
    )
    return (
        case_cfg,
        resolved_ability_col,
        resolved_db_url,
        resolved_outcome_col,
        resolved_random_seed,
        resolved_refresh_db,
        resolved_stage2_threshold,
        resolved_use_cache,
        run_cfg,
        specs_df,
        stage1_cfg,
        stage2_cfg,
    )


@app.cell
def _(case_cfg, mo, specs_df):
    # セル概要: 解析対象spec一覧とcase設定を表示する。
    preview = mo.vstack(
        [
            mo.md(f"Case ID: `{case_cfg.case_id}`"),
            mo.md(
                f"Ability: `{case_cfg.ability_col}` / transform `{case_cfg.ability_transform}` / rope `{case_cfg.rope}`"
            ),
            mo.md("### Specs"),
            specs_df,
        ]
    )
    preview
    return


@app.cell
def _(date, project_root):
    # セル概要: 出力先パスを準備する。
    today = date.today().strftime("%Y%m%d")
    output_root = project_root / "notebook" / "lab" / "tmp" / "group_condition_glmm_runs"
    report_results_dir = project_root / "notebook" / "report" / "results"
    report_features_dir = project_root / "notebook" / "report" / "features"
    logs_dir = project_root / "outputs" / f"glmm_condition_aptitude_generic_marimo_logs_{today}"

    output_root.mkdir(parents=True, exist_ok=True)
    report_results_dir.mkdir(parents=True, exist_ok=True)
    report_features_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    aggregate_runs_path = report_results_dir / f"{today}_glmm_condition_aptitude_generic_runs.csv"
    aggregate_compare_path = report_results_dir / f"{today}_glmm_condition_aptitude_generic_compare.csv"
    report_path = report_features_dir / f"{today}_glmm_condition_aptitude_generic_report.md"
    return (
        aggregate_compare_path,
        aggregate_runs_path,
        logs_dir,
        output_root,
        report_path,
    )


@app.cell
def _(
    build_cache_path,
    build_required_columns,
    case_cfg,
    create_engine,
    dataframe_cache_exists,
    load_dataframe_cache,
    pd,
    project_root,
    resolve_dataframe_cache_path,
    resolved_ability_col,
    resolved_db_url,
    resolved_outcome_col,
    resolved_refresh_db,
    resolved_use_cache,
    run_cfg,
    save_dataframe_cache,
    specs_df,
    text,
):
    # セル概要: DBから必要列を動的に読み込み、キャッシュを利用してデータを解決する。
    select_cols = build_required_columns(
        outcome_col=resolved_outcome_col,
        ability_col=resolved_ability_col,
        specs_df=specs_df,
    )
    cache_path = build_cache_path(
        project_root=project_root,
        run_cfg=run_cfg,
        outcome_col=resolved_outcome_col,
        ability_col=resolved_ability_col,
        ability_transform=case_cfg.ability_transform,
        specs_df=specs_df,
    )

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
            SELECT {", ".join(select_cols)}
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
    return df, select_cols


@app.cell
def _(df, mo):
    # セル概要: 入力データの件数と先頭行を表示する。
    view = mo.vstack(
        [
            mo.md(f"Rows: `{len(df):,}`"),
            df.head(8),
        ]
    )
    view
    return


@app.cell
def _(is_script_mode, run_button):
    # セル概要: scriptでは自動実行、interactiveではボタンクリックで実行する。
    should_run = is_script_mode or bool(run_button.value)
    return (should_run,)


@app.cell
def _(
    save_stage_artifacts,
    aggregate_compare_path,
    aggregate_runs_path,
    build_aggregate_tables,
    case_cfg,
    datetime,
    df,
    json,
    logs_dir,
    output_root,
    render_report_markdown,
    report_path,
    resolved_outcome_col,
    resolved_random_seed,
    resolved_stage2_threshold,
    run_cfg,
    run_stage_for_specs,
    select_stage2_targets,
    should_run,
    stage1_cfg,
    stage2_cfg,
):
    # セル概要: 単一caseを実行し、集約結果と成果物を保存する。
    compare_df = None
    results_df = None
    run_summary = {
        "status": "idle",
        "message": "Press `Run GLMM` to start.",
    }

    if should_run:
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_root = output_root / session_ts
        case_dir = session_root / case_cfg.case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        all_results = []
        stage2_targets_by_case: dict[str, list[str]] = {}

        stage1_results, stage1_artifacts = run_stage_for_specs(
            df,
            run_cfg,
            case_cfg,
            stage1_cfg,
            stage="stage1",
            outcome_col=resolved_outcome_col,
            random_seed=resolved_random_seed,
        )
        all_results.extend(stage1_results)
        path_map = save_stage_artifacts(
            case_dir=case_dir,
            case_cfg=case_cfg,
            logs_dir=logs_dir,
            results=stage1_results,
            artifacts=stage1_artifacts,
        )

        if run_cfg.stage_mode == "stage1_stage2":
            stage2_targets = select_stage2_targets(
                stage1_results,
                threshold=resolved_stage2_threshold,
            )
            stage2_targets_by_case[case_cfg.case_id] = stage2_targets
            if stage2_targets:
                target_set = set(stage2_targets)
                stage2_case_cfg = case_cfg.__class__(
                    case_id=case_cfg.case_id,
                    ability_col=case_cfg.ability_col,
                    ability_transform=case_cfg.ability_transform,
                    rope=case_cfg.rope,
                    group_condition_specs=tuple(
                        spec
                        for spec in case_cfg.group_condition_specs
                        if spec.model_id in target_set
                    ),
                )
                stage2_results, stage2_artifacts = run_stage_for_specs(
                    df,
                    run_cfg,
                    stage2_case_cfg,
                    stage2_cfg,
                    stage="stage2",
                    outcome_col=resolved_outcome_col,
                    random_seed=resolved_random_seed + 100,
                )
                all_results.extend(stage2_results)
                path_map.update(
                    save_stage_artifacts(
                        case_dir=case_dir,
                        case_cfg=case_cfg,
                        logs_dir=logs_dir,
                        results=stage2_results,
                        artifacts=stage2_artifacts,
                    )
                )

        results_df, compare_df = build_aggregate_tables(all_results)
        results_df.to_csv(aggregate_runs_path, index=False)
        compare_df.to_csv(aggregate_compare_path, index=False)

        report_text = render_report_markdown(
            run_cfg=run_cfg,
            case_configs=[case_cfg],
            stage1_cfg_by_case={case_cfg.case_id: stage1_cfg},
            stage2_cfg_by_case={case_cfg.case_id: stage2_cfg},
            results_df=results_df,
            compare_df=compare_df,
            stage2_targets_by_case=stage2_targets_by_case if stage2_targets_by_case else None,
            created_at=datetime.now().isoformat(timespec="seconds"),
            title="GLMM条件別適性検証レポート（marimo汎用版）",
        )
        report_path.write_text(report_text, encoding="utf-8")

        runs_with_paths = results_df.copy()
        runs_with_paths["summary_path"] = runs_with_paths.apply(
            lambda row: path_map.get((row["stage"], row["model_id"]), {}).get("summary_path", ""),
            axis=1,
        )
        runs_with_paths["ranking_path"] = runs_with_paths.apply(
            lambda row: path_map.get((row["stage"], row["model_id"]), {}).get("ranking_path", ""),
            axis=1,
        )
        runs_with_paths["config_path"] = runs_with_paths.apply(
            lambda row: path_map.get((row["stage"], row["model_id"]), {}).get("config_path", ""),
            axis=1,
        )
        runs_with_paths.to_csv(aggregate_runs_path, index=False)
        results_df = runs_with_paths

        run_summary = {
            "status": "completed",
            "session_root": str(session_root),
            "aggregate_runs_path": str(aggregate_runs_path),
            "aggregate_compare_path": str(aggregate_compare_path),
            "report_path": str(report_path),
            "case_id": case_cfg.case_id,
            "spec_count": len(case_cfg.group_condition_specs),
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
                mo.md("## 実行結果"),
                mo.md(f"Session: `{run_summary['session_root']}`"),
                mo.md(f"Case ID: `{run_summary['case_id']}` / Specs: `{run_summary['spec_count']}`"),
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
