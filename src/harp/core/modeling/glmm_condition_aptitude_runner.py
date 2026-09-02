from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import arviz as az
import numpy as np
import pandas as pd

from harp.core.modeling.group_condition_categorical_glmm import (
    build_group_condition_categorical_glmm_model,
    prepare_group_condition_categorical_glmm_data,
    sample_group_condition_categorical_glmm,
)

ABILITY_TRANSFORMS = ("none", "log", "z", "log_z")
STAGE_MODES = ("stage1", "stage1_stage2")


@dataclass(frozen=True)
class GroupConditionSpec:
    model_id: str
    group_col: str
    condition_col: str


@dataclass(frozen=True)
class SamplingStageConfig:
    draws: int
    tune: int
    chains: int
    cores: int
    target_accept: float


@dataclass(frozen=True)
class AptitudeRunConfig:
    table: str
    start_date: str
    race_level_min: int
    race_level_max: int
    row_limit: int
    min_group_count: int
    min_cell_count: int
    min_condition_levels: int
    stage_mode: str = "stage1"

    def validate(self) -> None:
        if self.race_level_min > self.race_level_max:
            raise ValueError("race_level_min must be <= race_level_max")
        if self.row_limit <= 0:
            raise ValueError("row_limit must be positive")
        if self.min_group_count <= 0:
            raise ValueError("min_group_count must be > 0")
        if self.min_cell_count <= 0:
            raise ValueError("min_cell_count must be > 0")
        if self.min_condition_levels <= 0:
            raise ValueError("min_condition_levels must be > 0")
        if self.stage_mode not in STAGE_MODES:
            raise ValueError(f"Invalid stage_mode: {self.stage_mode}")


@dataclass(frozen=True)
class AptitudeCaseConfig:
    case_id: str
    ability_col: str
    ability_transform: str
    rope: float
    group_condition_specs: tuple[GroupConditionSpec, ...]

    def validate(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must not be empty")
        if not self.ability_col:
            raise ValueError("ability_col must not be empty")
        if self.ability_transform not in ABILITY_TRANSFORMS:
            raise ValueError(f"Invalid ability_transform: {self.ability_transform}")
        if self.rope <= 0.0:
            raise ValueError("rope must be > 0")
        if not self.group_condition_specs:
            raise ValueError("group_condition_specs must not be empty")


@dataclass(frozen=True)
class AptitudeCaseResult:
    case_id: str
    model_id: str
    group_col: str
    condition_col: str
    stage: str
    status: str
    error_message: str
    n_obs: int
    n_groups: int
    n_conditions: int
    sparse_drop_ratio: float
    sigma_gc_mean: float
    sigma_gc_hdi_low: float
    sigma_gc_hdi_high: float
    p_sigma_gc_gt_rope: float
    global_aptitude_flag: bool
    local_aptitude_count: int


def _sanitize_name(name: str) -> str:
    sanitized = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(name))
    return sanitized.strip("_") or "x"


def default_group_condition_specs() -> tuple[GroupConditionSpec, ...]:
    return (
        GroupConditionSpec("jockey_x_distance_bucket_4", "jockey_cd", "distance_bucket_4"),
        GroupConditionSpec("jockey_x_jyo_cd", "jockey_cd", "jyo_cd"),
        GroupConditionSpec("jockey_x_course_cluster", "jockey_cd", "course_cluster"),
        GroupConditionSpec("sire_x_distance_bucket_4", "sire_id", "distance_bucket_4"),
        GroupConditionSpec("sire_x_jyo_cd", "sire_id", "jyo_cd"),
        GroupConditionSpec("sire_x_course_cluster", "sire_id", "course_cluster"),
    )


def default_case_presets(
    *,
    rope: float = 0.05,
    group_specs: tuple[GroupConditionSpec, ...] | None = None,
) -> dict[str, AptitudeCaseConfig]:
    specs = default_group_condition_specs() if group_specs is None else group_specs
    return {
        "odds_log_z_ta097": AptitudeCaseConfig(
            case_id="odds_log_z_ta097",
            ability_col="odds_tansho",
            ability_transform="log_z",
            rope=float(rope),
            group_condition_specs=specs,
        ),
        "pos4_z_ta090": AptitudeCaseConfig(
            case_id="pos4_z_ta090",
            ability_col="pos4_agari_synergy_wavg5_recent_z",
            ability_transform="none",
            rope=float(rope),
            group_condition_specs=specs,
        ),
    }


def default_stage1_target_accept_by_case() -> dict[str, float]:
    return {
        "odds_log_z_ta097": 0.97,
        "pos4_z_ta090": 0.90,
    }


def to_distance_bucket_4(series: pd.Series, source_col: str = "distance_m") -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any():
        raise ValueError(f"`{source_col}` contains non-numeric or NA rows for distance bucket.")

    bucket = pd.Series(index=series.index, dtype="object")
    bucket = bucket.mask(values <= 1400, "dist_le_1400")
    bucket = bucket.mask((values >= 1500) & (values <= 1700), "dist_1500_1700")
    bucket = bucket.mask((values >= 1800) & (values <= 2100), "dist_1800_2100")
    bucket = bucket.mask(values >= 2200, "dist_ge_2200")
    return bucket


def prepare_ability_feature(
    df: pd.DataFrame,
    ability_col: str,
    transform: str,
) -> tuple[pd.DataFrame, str]:
    if transform not in ABILITY_TRANSFORMS:
        raise ValueError(f"Invalid transform: {transform}")
    if ability_col not in df.columns:
        raise KeyError(f"ability_col not found: {ability_col}")

    out = df.copy()
    base = pd.to_numeric(out[ability_col], errors="coerce")
    out[ability_col] = base
    current_col = ability_col

    if transform in {"log", "log_z"}:
        log_col = f"{ability_col}_log"
        safe_base = base.where(base > 0.0, np.nan)
        out[log_col] = np.log(np.clip(safe_base.to_numpy(copy=True), a_min=1e-6, a_max=None))
        current_col = log_col

    if transform in {"z", "log_z"}:
        z_col = f"{current_col}_z"
        src = pd.to_numeric(out[current_col], errors="coerce")
        mean = float(src.mean())
        std = float(src.std(ddof=0))
        if not np.isfinite(std) or std <= 0.0:
            std = 1.0
        out[z_col] = (src - mean) / std
        current_col = z_col

    return out, current_col


def _hdi95(samples: np.ndarray) -> tuple[float, float]:
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def _build_ranking_df(
    idata,
    group_codes: tuple[str, ...],
    condition_codes: tuple[str, ...],
    *,
    rope: float,
) -> pd.DataFrame:
    gc_samples = idata.posterior["group_condition"].to_numpy()
    flat = gc_samples.reshape((-1, gc_samples.shape[-2], gc_samples.shape[-1]))
    mean = flat.mean(axis=0)
    low = np.quantile(flat, 0.025, axis=0)
    high = np.quantile(flat, 0.975, axis=0)
    p_abs_gt_rope = np.mean(np.abs(flat) > rope, axis=0)
    is_local = ((low > rope) | (high < -rope)) & (p_abs_gt_rope >= 0.95)

    rows: list[dict[str, object]] = []
    for g_idx, g_code in enumerate(group_codes):
        for c_idx, c_code in enumerate(condition_codes):
            rows.append(
                {
                    "group": g_code,
                    "condition": c_code,
                    "effect_mean": float(mean[g_idx, c_idx]),
                    "hdi95_low": float(low[g_idx, c_idx]),
                    "hdi95_high": float(high[g_idx, c_idx]),
                    "p_abs_gt_rope": float(p_abs_gt_rope[g_idx, c_idx]),
                    "local_aptitude_flag": bool(is_local[g_idx, c_idx]),
                }
            )

    return (
        pd.DataFrame(rows)
        .sort_values(["p_abs_gt_rope", "effect_mean"], ascending=[False, False], ignore_index=True)
    )


def _build_summary_df(idata, ability_effect_col: str) -> pd.DataFrame:
    beta_ability = f"beta_{_sanitize_name(ability_effect_col)}"
    candidate = ["beta0", beta_ability, "sigma_group", "sigma_condition", "sigma_group_condition"]
    names = set(idata.posterior.data_vars.keys())
    var_names = [name for name in candidate if name in names]
    if not var_names:
        return pd.DataFrame()
    return az.summary(idata, var_names=var_names, kind="stats", hdi_prob=0.95)


def run_stage_for_specs(
    df: pd.DataFrame,
    run_cfg: AptitudeRunConfig,
    case_cfg: AptitudeCaseConfig,
    stage_cfg: SamplingStageConfig,
    *,
    stage: str = "stage1",
    outcome_col: str = "is_place",
    random_seed: int = 42,
) -> tuple[list[AptitudeCaseResult], dict[str, dict[str, Any]]]:
    run_cfg.validate()
    case_cfg.validate()

    if stage not in {"stage1", "stage2"}:
        raise ValueError(f"Invalid stage: {stage}")

    df_case, ability_effect_col = prepare_ability_feature(
        df,
        ability_col=case_cfg.ability_col,
        transform=case_cfg.ability_transform,
    )

    results: list[AptitudeCaseResult] = []
    artifacts: dict[str, dict[str, Any]] = {}

    for idx, spec in enumerate(case_cfg.group_condition_specs):
        try:
            glmm_data = prepare_group_condition_categorical_glmm_data(
                df_case,
                outcome_col=outcome_col,
                group_col=spec.group_col,
                condition_col=spec.condition_col,
                odds_col=None,
                extra_fixed_effect_cols=[ability_effect_col],
                min_group_count=run_cfg.min_group_count,
                min_cell_count=run_cfg.min_cell_count,
                min_condition_levels_per_group=run_cfg.min_condition_levels,
            )
            model = build_group_condition_categorical_glmm_model(glmm_data)
            idata = sample_group_condition_categorical_glmm(
                model,
                draws=stage_cfg.draws,
                tune=stage_cfg.tune,
                chains=stage_cfg.chains,
                cores=stage_cfg.cores,
                target_accept=stage_cfg.target_accept,
                random_seed=random_seed + idx,
                progressbar=True,
            )

            ranking_df = _build_ranking_df(
                idata,
                glmm_data.group_codes,
                glmm_data.condition_codes,
                rope=case_cfg.rope,
            )
            summary_df = _build_summary_df(idata, ability_effect_col)

            sigma_samples = idata.posterior["sigma_group_condition"].to_numpy().reshape(-1)
            sigma_mean = float(np.mean(sigma_samples))
            sigma_low, sigma_high = _hdi95(sigma_samples)
            p_sigma_gt_rope = float(np.mean(sigma_samples > case_cfg.rope))
            global_flag = bool((sigma_low > case_cfg.rope) and (p_sigma_gt_rope >= 0.95))
            local_count = int(ranking_df["local_aptitude_flag"].sum())

            result = AptitudeCaseResult(
                case_id=case_cfg.case_id,
                model_id=spec.model_id,
                group_col=spec.group_col,
                condition_col=spec.condition_col,
                stage=stage,
                status="ok",
                error_message="",
                n_obs=glmm_data.n_obs,
                n_groups=glmm_data.n_groups,
                n_conditions=glmm_data.n_conditions,
                sparse_drop_ratio=float(glmm_data.filter_stats.sparse_drop_ratio),
                sigma_gc_mean=sigma_mean,
                sigma_gc_hdi_low=sigma_low,
                sigma_gc_hdi_high=sigma_high,
                p_sigma_gc_gt_rope=p_sigma_gt_rope,
                global_aptitude_flag=global_flag,
                local_aptitude_count=local_count,
            )
            results.append(result)
            artifacts[spec.model_id] = {
                "summary_df": summary_df,
                "ranking_df": ranking_df,
                "config": {
                    "run": asdict(run_cfg),
                    "case": asdict(case_cfg),
                    "stage": stage,
                    "sampling": asdict(stage_cfg),
                    "ability_effect_col": ability_effect_col,
                },
                "error": None,
            }
        except Exception as exc:  # pragma: no cover - tested by status/error fields
            result = AptitudeCaseResult(
                case_id=case_cfg.case_id,
                model_id=spec.model_id,
                group_col=spec.group_col,
                condition_col=spec.condition_col,
                stage=stage,
                status="error",
                error_message=str(exc),
                n_obs=0,
                n_groups=0,
                n_conditions=0,
                sparse_drop_ratio=0.0,
                sigma_gc_mean=float("nan"),
                sigma_gc_hdi_low=float("nan"),
                sigma_gc_hdi_high=float("nan"),
                p_sigma_gc_gt_rope=float("nan"),
                global_aptitude_flag=False,
                local_aptitude_count=0,
            )
            results.append(result)
            artifacts[spec.model_id] = {
                "summary_df": pd.DataFrame(),
                "ranking_df": pd.DataFrame(),
                "config": {
                    "run": asdict(run_cfg),
                    "case": asdict(case_cfg),
                    "stage": stage,
                    "sampling": asdict(stage_cfg),
                    "ability_effect_col": ability_effect_col,
                },
                "error": str(exc),
            }

    return results, artifacts


def select_stage2_targets(
    stage1_results: list[AptitudeCaseResult],
    *,
    threshold: float,
    fallback_top_k: int = 2,
) -> list[str]:
    success = [r for r in stage1_results if r.status == "ok"]
    if not success:
        return []

    passed = [r.model_id for r in success if r.p_sigma_gc_gt_rope >= threshold]
    if passed:
        return passed

    ranked = sorted(success, key=lambda r: r.p_sigma_gc_gt_rope, reverse=True)
    return [r.model_id for r in ranked[: max(1, int(fallback_top_k))]]


def build_aggregate_tables(
    results: list[AptitudeCaseResult],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not results:
        return pd.DataFrame(), pd.DataFrame()

    results_df = pd.DataFrame([asdict(r) for r in results]).sort_values(
        ["stage", "case_id", "model_id"],
        ignore_index=True,
    )

    compare_rows: list[dict[str, Any]] = []
    grouped = results_df.groupby(["stage", "model_id"], dropna=False)
    for (stage, model_id), gdf in grouped:
        gdf = gdf.sort_values("case_id", ignore_index=True)
        baseline = gdf.iloc[0]
        baseline_case_id = str(baseline["case_id"])
        baseline_sigma = baseline["sigma_gc_mean"]
        baseline_local = baseline["local_aptitude_count"]

        for _, row in gdf.iterrows():
            sigma = row["sigma_gc_mean"]
            local_count = row["local_aptitude_count"]
            compare_rows.append(
                {
                    "stage": stage,
                    "model_id": model_id,
                    "baseline_case_id": baseline_case_id,
                    "case_id": row["case_id"],
                    "status": row["status"],
                    "sigma_gc_mean": sigma,
                    "delta_sigma_gc_mean_vs_baseline": sigma - baseline_sigma,
                    "local_aptitude_count": local_count,
                    "delta_local_aptitude_count_vs_baseline": local_count - baseline_local,
                    "p_sigma_gc_gt_rope": row["p_sigma_gc_gt_rope"],
                    "global_aptitude_flag": row["global_aptitude_flag"],
                }
            )

    compare_df = pd.DataFrame(compare_rows).sort_values(
        ["stage", "model_id", "case_id"], ignore_index=True
    )
    return results_df, compare_df


def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "(no rows)"
    out_df = df.loc[:, columns].copy()
    headers = [str(c) for c in out_df.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in out_df.iterrows():
        values = [str(row[c]) for c in out_df.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_report_markdown(
    *,
    run_cfg: AptitudeRunConfig,
    case_configs: list[AptitudeCaseConfig],
    stage1_cfg_by_case: dict[str, SamplingStageConfig],
    stage2_cfg_by_case: dict[str, SamplingStageConfig],
    results_df: pd.DataFrame,
    compare_df: pd.DataFrame,
    stage2_targets_by_case: dict[str, list[str]] | None = None,
    created_at: str,
    title: str = "GLMM条件別適性検証レポート（marimo汎用基盤）",
) -> str:
    sections: list[str] = [f"# {title}", "", "## 0. 実行情報"]
    sections.append(f"- 実行日時: {created_at}")
    sections.append(f"- table: `{run_cfg.table}`")
    sections.append(
        f"- 対象期間: `held_date >= {run_cfg.start_date}` / race_level `{run_cfg.race_level_min}..{run_cfg.race_level_max}`"
    )
    sections.append(
        f"- sparseしきい値: group>={run_cfg.min_group_count}, cell>={run_cfg.min_cell_count}, condition_levels>={run_cfg.min_condition_levels}"
    )
    sections.append(f"- stage_mode: `{run_cfg.stage_mode}`")

    sections.append("")
    sections.append("## 1. ケース設定")
    case_rows = []
    for case in case_configs:
        stage1 = stage1_cfg_by_case[case.case_id]
        stage2 = stage2_cfg_by_case[case.case_id]
        case_rows.append(
            {
                "case_id": case.case_id,
                "ability_col": case.ability_col,
                "ability_transform": case.ability_transform,
                "rope": case.rope,
                "stage1_target_accept": stage1.target_accept,
                "stage2_target_accept": stage2.target_accept,
            }
        )
    sections.append(_markdown_table(pd.DataFrame(case_rows), list(case_rows[0].keys()) if case_rows else []))

    sections.append("")
    sections.append("## 2. 実行結果（集約）")
    sections.append(
        _markdown_table(
            results_df,
            [
                "case_id",
                "stage",
                "model_id",
                "status",
                "n_obs",
                "n_groups",
                "n_conditions",
                "sigma_gc_mean",
                "sigma_gc_hdi_low",
                "sigma_gc_hdi_high",
                "p_sigma_gc_gt_rope",
                "global_aptitude_flag",
                "local_aptitude_count",
            ],
        )
    )

    sections.append("")
    sections.append("## 3. ケース比較")
    sections.append(
        _markdown_table(
            compare_df,
            [
                "stage",
                "model_id",
                "baseline_case_id",
                "case_id",
                "status",
                "sigma_gc_mean",
                "delta_sigma_gc_mean_vs_baseline",
                "local_aptitude_count",
                "delta_local_aptitude_count_vs_baseline",
                "global_aptitude_flag",
            ],
        )
    )

    if stage2_targets_by_case:
        sections.append("")
        sections.append("## 4. Stage2選抜")
        for case_id, targets in stage2_targets_by_case.items():
            sections.append(f"- {case_id}: {', '.join(targets) if targets else '(なし)'}")

    sections.append("")
    sections.append("## 5. 判定基準")
    sections.append("- グローバル: HDI95_low(sigma_gc) > rope && P(sigma_gc > rope) >= 0.95")
    sections.append("- 局所: HDI95(effect[g,c]) がROPE外 && P(|effect| > rope) >= 0.95")

    return "\n".join(sections) + "\n"
