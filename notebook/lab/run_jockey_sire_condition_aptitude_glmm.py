from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harp.adapters.driven.storage import (  # noqa: E402
    dataframe_cache_exists,
    load_dataframe_cache,
    resolve_dataframe_cache_path,
    save_dataframe_cache,
)
from harp.core.modeling import (  # noqa: E402
    AptitudeCaseConfig,
    AptitudeRunConfig,
    GroupConditionSpec,
    SamplingStageConfig,
    build_aggregate_tables,
    default_group_condition_specs,
    render_report_markdown,
    run_stage_for_specs,
    select_stage2_targets,
    to_distance_bucket_4,
)
from harp.shared.paths import notebook_analysis_cache_dir  # noqa: E402
from pipeline.runtime_settings import load_pipeline_runtime_config  # noqa: E402


@dataclass(frozen=True)
class CliConfig:
    db_url: str
    table: str
    start_date: str
    race_level_min: int
    race_level_max: int
    row_limit: int
    use_cache: bool
    refresh_db: bool
    outcome_col: str
    ability_col: str
    ability_transform: str
    rope: float
    min_group_count: int
    min_cell_count: int
    min_condition_levels: int
    stage1: SamplingStageConfig
    stage2: SamplingStageConfig
    stage2_p_threshold: float
    stage1_only: bool
    random_seed: int
    output_dir: Path
    results_csv_path: Path
    report_path: Path
    log_dir: Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run staged GLMM aptitude validation for jockey/sire x condition combinations.",
    )
    parser.add_argument("--db-url", type=str, default="", help="PostgreSQL URL. Defaults to env HARP_DB_URL.")
    parser.add_argument("--table", type=str, default="mart.m_train_race_horse_past5")
    parser.add_argument("--start-date", type=str, default="2023-01-01")
    parser.add_argument("--race-level-min", type=int, default=1)
    parser.add_argument("--race-level-max", type=int, default=3)
    parser.add_argument("--row-limit", type=int, default=200_000)
    parser.add_argument("--no-cache", action="store_true", help="Disable cache read/write.")
    parser.add_argument("--refresh-db", action="store_true", help="Force DB read and overwrite cache.")

    parser.add_argument("--outcome-col", type=str, default="is_place")
    parser.add_argument("--ability-col", type=str, default="pos4_agari_synergy_wavg5_recent")
    parser.add_argument(
        "--ability-transform",
        type=str,
        choices=["none", "log", "z", "log_z"],
        default="none",
        help="Optional transform for fixed-effect ability column.",
    )
    parser.add_argument("--rope", type=float, default=0.05)

    parser.add_argument("--min-group-count", type=int, default=100)
    parser.add_argument("--min-cell-count", type=int, default=5)
    parser.add_argument("--min-condition-levels", type=int, default=2)

    parser.add_argument("--draws", type=int, default=300, help="Stage1 draws")
    parser.add_argument("--tune", type=int, default=300, help="Stage1 tune")
    parser.add_argument("--chains", type=int, default=2, help="Stage1 chains")
    parser.add_argument("--cores", type=int, default=1, help="Stage1 cores")
    parser.add_argument("--target-accept", type=float, default=0.90, help="Stage1 target_accept")

    parser.add_argument("--stage2-draws", type=int, default=1000)
    parser.add_argument("--stage2-tune", type=int, default=1000)
    parser.add_argument("--stage2-chains", type=int, default=2)
    parser.add_argument("--stage2-cores", type=int, default=1)
    parser.add_argument("--stage2-target-accept", type=float, default=0.95)
    parser.add_argument("--stage2-p-threshold", type=float, default=0.80)
    parser.add_argument("--stage1-only", action="store_true")

    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "notebook" / "lab" / "tmp" / "group_condition_glmm_runs"),
    )
    parser.add_argument("--results-csv", type=str, default="")
    parser.add_argument("--report-path", type=str, default="")
    parser.add_argument("--log-dir", type=str, default="")
    return parser.parse_args()


def _validate_table_name(table_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", table_name):
        raise ValueError(f"Invalid table name: {table_name}")


def _build_config(args: argparse.Namespace) -> CliConfig:
    runtime_config = load_pipeline_runtime_config()
    db_url = args.db_url.strip() or runtime_config.database.db_url
    if not db_url:
        raise ValueError("db-url is required (either --db-url or HARP_DB_URL).")
    if args.race_level_min > args.race_level_max:
        raise ValueError("race-level-min must be <= race-level-max")
    if args.row_limit <= 0:
        raise ValueError("row-limit must be positive")
    if args.rope <= 0:
        raise ValueError("rope must be > 0")

    _validate_table_name(args.table)

    today = date.today().strftime("%Y%m%d")

    def _resolve_path(raw: str, default_path: Path) -> Path:
        candidate = Path(raw) if raw.strip() else default_path
        if not candidate.is_absolute():
            return PROJECT_ROOT / candidate
        return candidate

    results_csv_path = _resolve_path(
        args.results_csv,
        PROJECT_ROOT / "notebook" / "report" / "results" / f"{today}_glmm_jockey_sire_condition_aptitude_runs.csv",
    )
    report_path = _resolve_path(
        args.report_path,
        PROJECT_ROOT / "notebook" / "report" / "features" / f"{today}_glmm_jockey_sire_condition_aptitude_validation_report.md",
    )
    log_dir = _resolve_path(
        args.log_dir,
        PROJECT_ROOT / "outputs" / f"glmm_condition_aptitude_logs_{today}",
    )

    return CliConfig(
        db_url=db_url,
        table=str(args.table).strip(),
        start_date=str(args.start_date).strip(),
        race_level_min=int(args.race_level_min),
        race_level_max=int(args.race_level_max),
        row_limit=int(args.row_limit),
        use_cache=not bool(args.no_cache),
        refresh_db=bool(args.refresh_db),
        outcome_col=str(args.outcome_col).strip(),
        ability_col=str(args.ability_col).strip(),
        ability_transform=str(args.ability_transform).strip(),
        rope=float(args.rope),
        min_group_count=int(args.min_group_count),
        min_cell_count=int(args.min_cell_count),
        min_condition_levels=int(args.min_condition_levels),
        stage1=SamplingStageConfig(
            draws=int(args.draws),
            tune=int(args.tune),
            chains=int(args.chains),
            cores=int(args.cores),
            target_accept=float(args.target_accept),
        ),
        stage2=SamplingStageConfig(
            draws=int(args.stage2_draws),
            tune=int(args.stage2_tune),
            chains=int(args.stage2_chains),
            cores=int(args.stage2_cores),
            target_accept=float(args.stage2_target_accept),
        ),
        stage2_p_threshold=float(args.stage2_p_threshold),
        stage1_only=bool(args.stage1_only),
        random_seed=int(args.random_seed),
        output_dir=Path(args.output_dir),
        results_csv_path=results_csv_path,
        report_path=report_path,
        log_dir=log_dir,
    )


def _build_cache_path(cfg: CliConfig) -> Path:
    cache_dir = notebook_analysis_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"glmm_aptitude_{cfg.table.replace('.', '_')}_"
        f"{cfg.outcome_col}_{cfg.ability_col}_{cfg.ability_transform}_"
        f"{cfg.start_date}_{cfg.race_level_min}_{cfg.race_level_max}_{cfg.row_limit}"
    )
    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)
    return cache_dir / f"{safe_stem}.parquet"


def _load_dataset(cfg: CliConfig) -> pd.DataFrame:
    needed_cols = [
        cfg.outcome_col,
        cfg.ability_col,
        "jockey_cd",
        "sire_id",
        "distance_m",
        "jyo_cd",
        "course_cluster",
    ]
    select_cols = ["race_id", "held_date", "race_level", *needed_cols]

    cache_path = _build_cache_path(cfg)
    if cfg.use_cache and dataframe_cache_exists(cache_path) and (not cfg.refresh_db):
        cache_source_path = resolve_dataframe_cache_path(cache_path)
        print(f"[cache] loading: {cache_source_path}")
        return load_dataframe_cache(cache_path)

    engine = create_engine(cfg.db_url)
    sql = text(
        f"""
        SELECT {", ".join(select_cols)}
        FROM {cfg.table}
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
                "start_date": cfg.start_date,
                "race_level_min": cfg.race_level_min,
                "race_level_max": cfg.race_level_max,
                "row_limit": cfg.row_limit,
            },
        )

    if df.empty:
        raise ValueError("Query returned 0 rows. Check filters and columns.")

    if cfg.use_cache:
        save_dataframe_cache(df, cache_path)
        print(f"[cache] saved: {cache_path}")

    return df


def _save_stage_artifacts(
    cfg: CliConfig,
    session_dir: Path,
    case_cfg: AptitudeCaseConfig,
    results,
    artifacts: dict[str, dict[str, object]],
) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    for res in results:
        run_name = f"{res.stage}_{res.model_id}"
        summary_path = ""
        ranking_path = ""
        config_path = ""

        artifact = artifacts.get(res.model_id, {})
        summary_df = artifact.get("summary_df", pd.DataFrame())
        ranking_df = artifact.get("ranking_df", pd.DataFrame())
        config_dict = artifact.get("config", {})
        error = artifact.get("error")

        if isinstance(summary_df, pd.DataFrame):
            path = session_dir / f"{run_name}_summary.csv"
            summary_df.to_csv(path, index=True)
            summary_path = str(path)
        if isinstance(ranking_df, pd.DataFrame):
            path = session_dir / f"{run_name}_group_condition_ranking.csv"
            ranking_df.to_csv(path, index=False)
            ranking_path = str(path)

        path = session_dir / f"{run_name}_config.json"
        payload = {
            "case_id": case_cfg.case_id,
            "ability_col": case_cfg.ability_col,
            "ability_transform": case_cfg.ability_transform,
            "rope": case_cfg.rope,
            "result": {
                "status": res.status,
                "error_message": res.error_message,
                "n_obs": res.n_obs,
                "n_groups": res.n_groups,
                "n_conditions": res.n_conditions,
                "sparse_drop_ratio": res.sparse_drop_ratio,
                "sigma_gc_mean": res.sigma_gc_mean,
                "sigma_gc_hdi_low": res.sigma_gc_hdi_low,
                "sigma_gc_hdi_high": res.sigma_gc_hdi_high,
                "p_sigma_gc_gt_rope": res.p_sigma_gc_gt_rope,
                "global_aptitude_flag": res.global_aptitude_flag,
                "local_aptitude_count": res.local_aptitude_count,
            },
            "runner_config": config_dict,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        config_path = str(path)

        log_payload = {
            "run_name": run_name,
            "model_id": res.model_id,
            "group_col": res.group_col,
            "condition_col": res.condition_col,
            "stage": res.stage,
            "case_id": case_cfg.case_id,
            "status": res.status,
            "error_message": res.error_message,
            "runner_error": error,
            "n_obs": res.n_obs,
            "n_groups": res.n_groups,
            "n_conditions": res.n_conditions,
            "sparse_drop_ratio": res.sparse_drop_ratio,
            "sigma_gc_mean": res.sigma_gc_mean,
            "sigma_gc_hdi_low": res.sigma_gc_hdi_low,
            "sigma_gc_hdi_high": res.sigma_gc_hdi_high,
            "p_sigma_gc_gt_rope": res.p_sigma_gc_gt_rope,
            "global_aptitude_flag": res.global_aptitude_flag,
            "local_aptitude_count": res.local_aptitude_count,
            "summary_path": summary_path,
            "ranking_path": ranking_path,
            "config_path": config_path,
        }
        (cfg.log_dir / f"{run_name}.json").write_text(
            json.dumps(log_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        out[(res.stage, res.model_id)] = {
            "summary_path": summary_path,
            "ranking_path": ranking_path,
            "config_path": config_path,
        }

    return out


def _to_results_csv_df(results, path_map: dict[tuple[str, str], dict[str, str]]) -> pd.DataFrame:
    rows = []
    for res in results:
        paths = path_map.get((res.stage, res.model_id), {})
        rows.append(
            {
                "model_id": res.model_id,
                "group_col": res.group_col,
                "condition_col": res.condition_col,
                "stage": res.stage,
                "status": res.status,
                "error_message": res.error_message,
                "n_obs": res.n_obs,
                "n_groups": res.n_groups,
                "n_conditions": res.n_conditions,
                "sparse_drop_ratio": res.sparse_drop_ratio,
                "sigma_gc_mean": res.sigma_gc_mean,
                "sigma_gc_hdi_low": res.sigma_gc_hdi_low,
                "sigma_gc_hdi_high": res.sigma_gc_hdi_high,
                "p_sigma_gc_gt_rope": res.p_sigma_gc_gt_rope,
                "global_aptitude_flag": "yes" if res.global_aptitude_flag else "no",
                "local_aptitude_count": res.local_aptitude_count,
                "summary_path": paths.get("summary_path", ""),
                "ranking_path": paths.get("ranking_path", ""),
                "config_path": paths.get("config_path", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_single_case_cfg(cfg: CliConfig, specs: tuple[GroupConditionSpec, ...]) -> AptitudeCaseConfig:
    case_id = f"{cfg.ability_col}_{cfg.ability_transform}".replace(" ", "_")
    return AptitudeCaseConfig(
        case_id=case_id,
        ability_col=cfg.ability_col,
        ability_transform=cfg.ability_transform,
        rope=cfg.rope,
        group_condition_specs=specs,
    )


def main() -> None:
    args = _parse_args()
    cfg = _build_config(args)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.results_csv_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.report_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = cfg.output_dir / session_ts
    session_dir.mkdir(parents=True, exist_ok=True)

    df = _load_dataset(cfg)
    df = df.copy()
    df["distance_bucket_4"] = to_distance_bucket_4(df["distance_m"])
    print(f"[data] rows={len(df):,}")

    specs = default_group_condition_specs()
    case_cfg = _build_single_case_cfg(cfg, specs)
    run_cfg = AptitudeRunConfig(
        table=cfg.table,
        start_date=cfg.start_date,
        race_level_min=cfg.race_level_min,
        race_level_max=cfg.race_level_max,
        row_limit=cfg.row_limit,
        min_group_count=cfg.min_group_count,
        min_cell_count=cfg.min_cell_count,
        min_condition_levels=cfg.min_condition_levels,
        stage_mode="stage1" if cfg.stage1_only else "stage1_stage2",
    )

    print(
        f"[case] ability_col={case_cfg.ability_col}, "
        f"transform={case_cfg.ability_transform}, rope={case_cfg.rope}"
    )

    stage1_results, stage1_artifacts = run_stage_for_specs(
        df,
        run_cfg,
        case_cfg,
        cfg.stage1,
        stage="stage1",
        outcome_col=cfg.outcome_col,
        random_seed=cfg.random_seed,
    )
    for res in stage1_results:
        print(
            f"[stage1] {res.model_id} status={res.status} "
            f"p_sigma_gc_gt_rope={res.p_sigma_gc_gt_rope if res.status == 'ok' else 'nan'}"
        )

    all_results = list(stage1_results)
    path_map = _save_stage_artifacts(cfg, session_dir, case_cfg, stage1_results, stage1_artifacts)

    stage2_targets: list[str] = []
    if not cfg.stage1_only:
        stage2_targets = select_stage2_targets(stage1_results, threshold=cfg.stage2_p_threshold)
        if stage2_targets:
            target_set = set(stage2_targets)
            stage2_specs = tuple(spec for spec in specs if spec.model_id in target_set)
            stage2_case_cfg = AptitudeCaseConfig(
                case_id=case_cfg.case_id,
                ability_col=case_cfg.ability_col,
                ability_transform=case_cfg.ability_transform,
                rope=case_cfg.rope,
                group_condition_specs=stage2_specs,
            )
            stage2_results, stage2_artifacts = run_stage_for_specs(
                df,
                run_cfg,
                stage2_case_cfg,
                cfg.stage2,
                stage="stage2",
                outcome_col=cfg.outcome_col,
                random_seed=cfg.random_seed + 100,
            )
            for res in stage2_results:
                print(
                    f"[stage2] {res.model_id} status={res.status} "
                    f"p_sigma_gc_gt_rope={res.p_sigma_gc_gt_rope if res.status == 'ok' else 'nan'}"
                )
            all_results.extend(stage2_results)
            path_map.update(_save_stage_artifacts(cfg, session_dir, case_cfg, stage2_results, stage2_artifacts))

    csv_df = _to_results_csv_df(all_results, path_map)
    csv_df.to_csv(cfg.results_csv_path, index=False)

    agg_results_df, compare_df = build_aggregate_tables(all_results)
    report_text = render_report_markdown(
        run_cfg=run_cfg,
        case_configs=[case_cfg],
        stage1_cfg_by_case={case_cfg.case_id: cfg.stage1},
        stage2_cfg_by_case={case_cfg.case_id: cfg.stage2},
        results_df=agg_results_df,
        compare_df=compare_df,
        stage2_targets_by_case={case_cfg.case_id: stage2_targets} if stage2_targets else None,
        created_at=datetime.now().isoformat(timespec="seconds"),
        title="GLMM条件別適性検証レポート（騎手・種牡馬）",
    )
    cfg.report_path.write_text(report_text, encoding="utf-8")

    print("[output]")
    print(f"- results_csv: {cfg.results_csv_path}")
    print(f"- report: {cfg.report_path}")
    print(f"- session_dir: {session_dir}")
    print(f"- log_dir: {cfg.log_dir}")


if __name__ == "__main__":
    main()
