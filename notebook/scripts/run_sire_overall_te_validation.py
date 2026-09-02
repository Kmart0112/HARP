from __future__ import annotations

import csv
import dataclasses
import json
import re
import subprocess
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = PROJECT_ROOT / "notebook" / "config" / "features.yml"
MODEL_EVAL_LOG_PATH = PROJECT_ROOT / "notebook" / "prd" / "outputs" / "model_eval_log.csv"
TODAY = date.today().strftime("%Y%m%d")
RUNS_CSV_PATH = (
    PROJECT_ROOT
    / "notebook"
    / "report"
    / "results"
    / f"{TODAY}_sire_overall_te_with_readd_exploration_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"sire_overall_te_logs_{TODAY}"

FORMAL_FEATURES = [
    "sire_avg_place_rate_smooth",
    "sire_avg_pos4_agari_synergy",
    "sire_avg_time_diff",
]
EXPLORATORY_FEATURES = [
    "same_cluster_sire_avg_place_rate_smooth",
    "same_surface_dist_pm200_sire_avg_place_rate",
    "same_age_sire_avg_place_rate_smooth_prev_age",
]

MARIMO_CMD = ["uv", "run", "python", "notebook/prd/lgbm_fuku_platt_metrics.py"]


@dataclasses.dataclass
class Metrics:
    timestamp: str
    auc: float
    logloss: float
    brier: float


def _set_feature_state(text: str, feature: str, enabled: bool) -> str:
    pattern = re.compile(rf"^(?P<indent>\s*)(?P<comment>#\s*)?-\s*{re.escape(feature)}\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"feature line not unique for '{feature}': found={len(matches)}")
    match = matches[0]
    indent = match.group("indent") or ""
    replacement = f"{indent}- {feature}" if enabled else f"{indent}# - {feature}"
    return text[: match.start()] + replacement + text[match.end() :]


def apply_feature_states(formal_enabled: set[str], exploratory_enabled: set[str]) -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    for feature in FORMAL_FEATURES:
        text = _set_feature_state(text, feature, feature in formal_enabled)
    for feature in EXPLORATORY_FEATURES:
        text = _set_feature_state(text, feature, feature in exploratory_enabled)
    FEATURES_PATH.write_text(text, encoding="utf-8")


def read_latest_metrics() -> Metrics:
    with MODEL_EVAL_LOG_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first = next(reader, None)
    if not first:
        raise ValueError("model_eval_log.csv is empty")
    return Metrics(
        timestamp=str(first["timestamp"]),
        auc=float(first["auc"]),
        logloss=float(first["logloss"]),
        brier=float(first["brier"]),
    )


def run_marimo(run_name: str) -> Metrics:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    before = read_latest_metrics().timestamp if MODEL_EVAL_LOG_PATH.exists() else ""
    proc = subprocess.run(
        MARIMO_CMD,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    log_path = RUN_LOG_DIR / f"{run_name}.log"
    log_path.write_text(proc.stdout + "\n\n[stderr]\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"run failed: {run_name} (see {log_path})")

    after = read_latest_metrics()
    if before and after.timestamp == before:
        raise RuntimeError(f"model_eval_log not updated for run: {run_name}")
    return after


def formal_decision(delta_auc: float, delta_logloss: float) -> str:
    if delta_auc > 0 and delta_logloss < 0:
        return "採用"
    if delta_auc > 0 or delta_logloss < 0:
        return "保留"
    return "不採用"


def choose_best_formal(rows: list[dict[str, object]]) -> dict[str, object]:
    candidates = [
        row
        for row in rows
        if row["scenario"] != "formal_baseline"
        and float(row["delta_auc_vs_formal_base"]) > 0
        and float(row["delta_logloss_vs_formal_base"]) < 0
    ]
    if not candidates:
        return next(row for row in rows if row["scenario"] == "formal_baseline")

    def _key(row: dict[str, object]) -> tuple[float, float, int, str]:
        return (
            float(row["delta_auc_vs_formal_base"]),
            -float(row["delta_logloss_vs_formal_base"]),
            -int(row["feature_count"]),
            str(row["scenario"]),
        )

    return max(candidates, key=_key)


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    formal_rows: list[dict[str, object]] = []
    all_rows: list[dict[str, object]] = []

    formal_scenarios = [
        ("formal_baseline", set()),
        ("formal_place_rate_only", {"sire_avg_place_rate_smooth"}),
        ("formal_pos4_only", {"sire_avg_pos4_agari_synergy"}),
        ("formal_time_diff_only", {"sire_avg_time_diff"}),
        ("formal_place_rate_pos4", {"sire_avg_place_rate_smooth", "sire_avg_pos4_agari_synergy"}),
        ("formal_place_rate_time_diff", {"sire_avg_place_rate_smooth", "sire_avg_time_diff"}),
        ("formal_pos4_time_diff", {"sire_avg_pos4_agari_synergy", "sire_avg_time_diff"}),
        (
            "formal_all_three",
            {"sire_avg_place_rate_smooth", "sire_avg_pos4_agari_synergy", "sire_avg_time_diff"},
        ),
    ]

    formal_base: Metrics | None = None

    for scenario, enabled in formal_scenarios:
        apply_feature_states(formal_enabled=enabled, exploratory_enabled=set())
        metrics = run_marimo(scenario)
        if scenario == "formal_baseline":
            formal_base = metrics
        assert formal_base is not None
        delta_auc = metrics.auc - formal_base.auc
        delta_logloss = metrics.logloss - formal_base.logloss
        delta_brier = metrics.brier - formal_base.brier
        decision = "基準" if scenario == "formal_baseline" else formal_decision(delta_auc, delta_logloss)
        row = {
            "mode": "formal",
            "scenario": scenario,
            "enabled_features": "|".join(sorted(enabled)),
            "feature_count": len(enabled),
            "timestamp": metrics.timestamp,
            "auc": f"{metrics.auc:.9f}",
            "logloss": f"{metrics.logloss:.9f}",
            "brier": f"{metrics.brier:.9f}",
            "delta_auc_vs_formal_base": f"{delta_auc:+.9f}",
            "delta_logloss_vs_formal_base": f"{delta_logloss:+.9f}",
            "delta_brier_vs_formal_base": f"{delta_brier:+.9f}",
            "decision": decision,
        }
        formal_rows.append(row)
        all_rows.append(row)
        print(
            f"[formal] {scenario}: auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, decision={decision}",
            flush=True,
        )

    best_formal = choose_best_formal(formal_rows)
    exp_base_features = set(str(best_formal["enabled_features"]).split("|")) if best_formal["enabled_features"] else set()
    exp_base_metrics = Metrics(
        timestamp=str(best_formal["timestamp"]),
        auc=float(best_formal["auc"]),
        logloss=float(best_formal["logloss"]),
        brier=float(best_formal["brier"]),
    )
    print(f"[formal] selected={best_formal['scenario']} features={sorted(exp_base_features)}", flush=True)

    exploratory_scenarios = [
        ("exploratory_add_same_cluster", {"same_cluster_sire_avg_place_rate_smooth"}),
        ("exploratory_add_same_surface_dist_pm200", {"same_surface_dist_pm200_sire_avg_place_rate"}),
        ("exploratory_add_same_age_prev_age", {"same_age_sire_avg_place_rate_smooth_prev_age"}),
        ("exploratory_add_all_three", set(EXPLORATORY_FEATURES)),
    ]

    for scenario, add_expl in exploratory_scenarios:
        apply_feature_states(formal_enabled=exp_base_features, exploratory_enabled=add_expl)
        metrics = run_marimo(scenario)
        delta_auc = metrics.auc - exp_base_metrics.auc
        delta_logloss = metrics.logloss - exp_base_metrics.logloss
        delta_brier = metrics.brier - exp_base_metrics.brier
        row = {
            "mode": "exploratory",
            "scenario": scenario,
            "enabled_features": "|".join(sorted(exp_base_features.union(add_expl))),
            "feature_count": len(exp_base_features.union(add_expl)),
            "timestamp": metrics.timestamp,
            "auc": f"{metrics.auc:.9f}",
            "logloss": f"{metrics.logloss:.9f}",
            "brier": f"{metrics.brier:.9f}",
            "delta_auc_vs_formal_base": f"{metrics.auc - formal_base.auc:+.9f}",
            "delta_logloss_vs_formal_base": f"{metrics.logloss - formal_base.logloss:+.9f}",
            "delta_brier_vs_formal_base": f"{metrics.brier - formal_base.brier:+.9f}",
            "delta_auc_vs_exp_base": f"{delta_auc:+.9f}",
            "delta_logloss_vs_exp_base": f"{delta_logloss:+.9f}",
            "delta_brier_vs_exp_base": f"{delta_brier:+.9f}",
            "decision": "保留",
        }
        all_rows.append(row)
        print(f"[exploratory] {scenario}: auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}", flush=True)

    apply_feature_states(formal_enabled=exp_base_features, exploratory_enabled=set())

    headers = [
        "mode",
        "scenario",
        "enabled_features",
        "feature_count",
        "timestamp",
        "auc",
        "logloss",
        "brier",
        "delta_auc_vs_formal_base",
        "delta_logloss_vs_formal_base",
        "delta_brier_vs_formal_base",
        "delta_auc_vs_exp_base",
        "delta_logloss_vs_exp_base",
        "delta_brier_vs_exp_base",
        "decision",
    ]
    with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in headers})

    summary = {
        "formal_baseline_scenario": "formal_baseline",
        "selected_formal_scenario": best_formal["scenario"],
        "selected_formal_features": sorted(exp_base_features),
        "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
        "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
