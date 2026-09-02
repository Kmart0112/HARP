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
    / f"{TODAY}_sire_usage_period_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"sire_usage_period_logs_{TODAY}"

SIRE_STARTS_FEATURE = "sire_starts_5y"
NEW_FEATURES = [
    "sire_career_months",
    "sire_is_early_phase_3y",
]
TARGET_FEATURES = [SIRE_STARTS_FEATURE, *NEW_FEATURES]

SCENARIOS: list[tuple[str, set[str]]] = [
    ("baseline_current", {SIRE_STARTS_FEATURE}),
    ("add_months", {SIRE_STARTS_FEATURE, "sire_career_months"}),
    ("add_early_flag", {SIRE_STARTS_FEATURE, "sire_is_early_phase_3y"}),
    ("add_both", {SIRE_STARTS_FEATURE, "sire_career_months", "sire_is_early_phase_3y"}),
    ("months_only", {"sire_career_months"}),
    ("early_only", {"sire_is_early_phase_3y"}),
    ("both_only", {"sire_career_months", "sire_is_early_phase_3y"}),
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


def decide(delta_auc: float, delta_logloss: float) -> str:
    if delta_auc > 0 and delta_logloss < 0:
        return "採用"
    if delta_auc > 0 or delta_logloss < 0:
        return "保留"
    return "不採用"


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    baseline: Metrics | None = None

    try:
        for scenario, enabled in SCENARIOS:
            apply_feature_states(enabled)
            metrics = run_metrics(scenario)
            if baseline is None:
                baseline = metrics

            delta_auc = metrics.auc - baseline.auc
            delta_logloss = metrics.logloss - baseline.logloss
            delta_brier = metrics.brier - baseline.brier
            decision = "基準" if scenario == "baseline_current" else decide(delta_auc, delta_logloss)

            rows.append(
                {
                    "scenario": scenario,
                    "enabled_features": "|".join(sorted(enabled)),
                    "feature_count": str(len(enabled)),
                    "timestamp": metrics.timestamp,
                    "auc": f"{metrics.auc:.9f}",
                    "logloss": f"{metrics.logloss:.9f}",
                    "brier": f"{metrics.brier:.9f}",
                    "delta_auc": f"{delta_auc:+.9f}",
                    "delta_logloss": f"{delta_logloss:+.9f}",
                    "delta_brier": f"{delta_brier:+.9f}",
                    "decision": decision,
                }
            )
            print(
                f"[{scenario}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, decision={decision}",
                flush=True,
            )
    finally:
        apply_feature_states({SIRE_STARTS_FEATURE})

    headers = [
        "scenario",
        "enabled_features",
        "feature_count",
        "timestamp",
        "auc",
        "logloss",
        "brier",
        "delta_auc",
        "delta_logloss",
        "delta_brier",
        "decision",
    ]
    with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    adopted_rows = [
        row
        for row in rows
        if row["scenario"] != "baseline_current"
        and float(row["delta_auc"]) > 0
        and float(row["delta_logloss"]) < 0
    ]
    if adopted_rows:
        best_row = max(
            adopted_rows,
            key=lambda r: (
                float(r["delta_auc"]),
                -float(r["delta_logloss"]),
                -int(r["feature_count"]),
                r["scenario"],
            ),
        )
    else:
        best_row = next(row for row in rows if row["scenario"] == "baseline_current")

    summary = {
        "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
        "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
        "best_scenario": best_row["scenario"],
        "best_enabled_features": best_row["enabled_features"],
        "best_delta_auc": best_row["delta_auc"],
        "best_delta_logloss": best_row["delta_logloss"],
        "best_decision": best_row["decision"],
        "restored_state": f"{SIRE_STARTS_FEATURE}=ON, new_features=OFF",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
