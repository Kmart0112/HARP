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
    / f"{TODAY}_jockey_cluster_vs_distance_jyo_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"jockey_cluster_vs_distance_jyo_logs_{TODAY}"

BASE_REQUIRED_FEATURES = {
    "jockey_avg_place_rate_smooth",
    "jockey_style_place_rate_3y_smooth",
}

CLUSTER_FEATURE = "jockey_cluster_avg_place_rate_corrected"
DISTANCE_EXACT_FEATURE = "jockey_surface_distance_place_rate_3y_smooth"
DISTANCE_PM200_FEATURE = "jockey_surface_dist_pm200_place_rate_3y_smooth"
JYO_FEATURE = "jockey_surface_jyo_place_rate_3y_smooth"

TARGET_FEATURES = {
    CLUSTER_FEATURE,
    DISTANCE_EXACT_FEATURE,
    DISTANCE_PM200_FEATURE,
    JYO_FEATURE,
}

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


def _is_feature_enabled(text: str, feature: str) -> bool:
    pattern = re.compile(rf"^\s*-\s*{re.escape(feature)}\s*$", re.MULTILINE)
    return bool(pattern.search(text))


def ensure_base_required_features_enabled() -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    missing = [feature for feature in sorted(BASE_REQUIRED_FEATURES) if not _is_feature_enabled(text, feature)]
    if missing:
        raise ValueError(f"required base feature is OFF in features.yml: {missing}")


def apply_feature_states(enabled: set[str]) -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    for feature in TARGET_FEATURES:
        text = _set_feature_state(text, feature, feature in enabled)
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


def run_metrics(run_name: str) -> Metrics:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    before = read_latest_metrics().timestamp if MODEL_EVAL_LOG_PATH.exists() else ""
    proc = subprocess.run(MARIMO_CMD, cwd=PROJECT_ROOT, text=True, capture_output=True)
    log_path = RUN_LOG_DIR / f"{run_name}.log"
    log_path.write_text(proc.stdout + "\n\n[stderr]\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"run failed: {run_name} (see {log_path})")
    after = read_latest_metrics()
    if before and after.timestamp == before:
        raise RuntimeError(f"model_eval_log not updated for run: {run_name}")
    return after


def _row(
    scenario: str,
    enabled: set[str],
    metrics: Metrics,
    base: Metrics,
    cluster: Metrics,
) -> dict[str, str]:
    delta_auc = metrics.auc - base.auc
    delta_logloss = metrics.logloss - base.logloss
    delta_brier = metrics.brier - base.brier
    delta_auc_vs_cluster = metrics.auc - cluster.auc
    delta_logloss_vs_cluster = metrics.logloss - cluster.logloss
    delta_brier_vs_cluster = metrics.brier - cluster.brier
    return {
        "scenario": scenario,
        "enabled_features": "|".join(sorted(enabled)),
        "timestamp": metrics.timestamp,
        "auc": f"{metrics.auc:.9f}",
        "logloss": f"{metrics.logloss:.9f}",
        "brier": f"{metrics.brier:.9f}",
        "delta_auc": f"{delta_auc:+.9f}",
        "delta_logloss": f"{delta_logloss:+.9f}",
        "delta_brier": f"{delta_brier:+.9f}",
        "delta_auc_vs_cluster": f"{delta_auc_vs_cluster:+.9f}",
        "delta_logloss_vs_cluster": f"{delta_logloss_vs_cluster:+.9f}",
        "delta_brier_vs_cluster": f"{delta_brier_vs_cluster:+.9f}",
        "better_than_cluster": "yes" if delta_auc_vs_cluster > 0 and delta_logloss_vs_cluster < 0 else "no",
    }


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    original_features_text = FEATURES_PATH.read_text(encoding="utf-8")
    success = False

    try:
        ensure_base_required_features_enabled()

        scenarios: dict[str, set[str]] = {
            "base_no_conditional": set(),
            "cluster_only": {CLUSTER_FEATURE},
            "distance_exact_only": {DISTANCE_EXACT_FEATURE},
            "distance_pm200_only": {DISTANCE_PM200_FEATURE},
            "jyo_only": {JYO_FEATURE},
            "distance_exact_jyo": {DISTANCE_EXACT_FEATURE, JYO_FEATURE},
            "distance_pm200_jyo": {DISTANCE_PM200_FEATURE, JYO_FEATURE},
            "distance_both_jyo": {DISTANCE_EXACT_FEATURE, DISTANCE_PM200_FEATURE, JYO_FEATURE},
        }

        rows: list[dict[str, str]] = []

        apply_feature_states(scenarios["base_no_conditional"])
        base_metrics = run_metrics("base_no_conditional")
        print(
            f"[base_no_conditional] auc={base_metrics.auc:.9f}, logloss={base_metrics.logloss:.9f}",
            flush=True,
        )

        apply_feature_states(scenarios["cluster_only"])
        cluster_metrics = run_metrics("cluster_only")
        row_cluster = _row(
            "cluster_only",
            scenarios["cluster_only"],
            cluster_metrics,
            base_metrics,
            cluster_metrics,
        )
        rows.append(row_cluster)
        print(
            f"[cluster_only] auc={cluster_metrics.auc:.9f}, logloss={cluster_metrics.logloss:.9f}",
            flush=True,
        )

        for scenario in (
            "distance_exact_only",
            "distance_pm200_only",
            "jyo_only",
            "distance_exact_jyo",
            "distance_pm200_jyo",
            "distance_both_jyo",
        ):
            enabled = scenarios[scenario]
            apply_feature_states(enabled)
            metrics = run_metrics(scenario)
            row = _row(scenario, enabled, metrics, base_metrics, cluster_metrics)
            rows.append(row)
            print(
                f"[{scenario}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, better_than_cluster={row['better_than_cluster']}",
                flush=True,
            )

        apply_feature_states({CLUSTER_FEATURE})

        headers = [
            "scenario",
            "enabled_features",
            "timestamp",
            "auc",
            "logloss",
            "brier",
            "delta_auc",
            "delta_logloss",
            "delta_brier",
            "delta_auc_vs_cluster",
            "delta_logloss_vs_cluster",
            "delta_brier_vs_cluster",
            "better_than_cluster",
        ]
        with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        better = [row for row in rows if row["better_than_cluster"] == "yes"]
        best_vs_cluster = min(rows[1:], key=lambda row: float(row["delta_logloss_vs_cluster"]))
        summary = {
            "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
            "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
            "cluster_feature": CLUSTER_FEATURE,
            "better_than_cluster_scenarios": [row["scenario"] for row in better],
            "best_logloss_vs_cluster_scenario": best_vs_cluster["scenario"],
            "best_logloss_vs_cluster_delta": best_vs_cluster["delta_logloss_vs_cluster"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        success = True
    finally:
        if not success:
            FEATURES_PATH.write_text(original_features_text, encoding="utf-8")


if __name__ == "__main__":
    main()
