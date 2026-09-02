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
    / f"{TODAY}_homestretch_slope_straight_distance_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"homestretch_slope_straight_distance_logs_{TODAY}"

TURN_DIRECTION_SURFACE_FEATURE = "same_turn_direction_surface_avg_pos4_agari_synergy"
HOMESTRETCH_SLOPE_SURFACE_FEATURE = "same_homestretch_slope_surface_avg_pos4_agari_synergy"
STRAIGHT_DISTANCE_BUCKET_SURFACE_FEATURE = "same_straight_distance_bucket_surface_avg_pos4_agari_synergy"
TARGET_FEATURES = {
    TURN_DIRECTION_SURFACE_FEATURE,
    HOMESTRETCH_SLOPE_SURFACE_FEATURE,
    STRAIGHT_DISTANCE_BUCKET_SURFACE_FEATURE,
}

SCENARIOS: list[tuple[str, set[str]]] = [
    ("baseline_existing", {TURN_DIRECTION_SURFACE_FEATURE}),
    (
        "homestretch_slope_surface_only",
        {TURN_DIRECTION_SURFACE_FEATURE, HOMESTRETCH_SLOPE_SURFACE_FEATURE},
    ),
    (
        "straight_distance_bucket_surface_only",
        {TURN_DIRECTION_SURFACE_FEATURE, STRAIGHT_DISTANCE_BUCKET_SURFACE_FEATURE},
    ),
    (
        "both_add",
        {
            TURN_DIRECTION_SURFACE_FEATURE,
            HOMESTRETCH_SLOPE_SURFACE_FEATURE,
            STRAIGHT_DISTANCE_BUCKET_SURFACE_FEATURE,
        },
    ),
    ("replace_turn_direction_surface_with_homestretch_slope_surface", {HOMESTRETCH_SLOPE_SURFACE_FEATURE}),
    ("replace_turn_direction_surface_with_straight_distance_bucket_surface", {STRAIGHT_DISTANCE_BUCKET_SURFACE_FEATURE}),
]

MARIMO_CMD = ["uv", "run", "python", "notebook/prd/lgbm_fuku_platt_metrics.py"]


@dataclasses.dataclass
class Metrics:
    timestamp: str
    auc: float
    logloss: float
    brier: float


def _set_feature_state(text: str, feature: str, enabled: bool) -> str:
    pattern = re.compile(
        rf"^(?P<indent>\s*)(?P<comment>#\s*)?-\s*{re.escape(feature)}\s*$",
        re.MULTILINE,
    )
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


def ensure_required_lines_present() -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    missing = [
        feature
        for feature in sorted(TARGET_FEATURES)
        if re.search(rf"^\s*(#\s*)?-\s*{re.escape(feature)}\s*$", text, re.MULTILINE) is None
    ]
    if missing:
        raise ValueError(f"features.yml missing feature lines: {missing}")


def ensure_baseline_feature_enabled() -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    if not _is_feature_enabled(text, TURN_DIRECTION_SURFACE_FEATURE):
        raise ValueError(
            f"required baseline feature is OFF in features.yml: {TURN_DIRECTION_SURFACE_FEATURE}"
        )


def apply_feature_states(enabled: set[str]) -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    for feature in TARGET_FEATURES:
        text = _set_feature_state(text, feature, feature in enabled)
    FEATURES_PATH.write_text(text, encoding="utf-8")


def read_latest_metrics() -> Metrics:
    if not MODEL_EVAL_LOG_PATH.exists():
        raise FileNotFoundError(f"metrics log not found: {MODEL_EVAL_LOG_PATH}")
    with MODEL_EVAL_LOG_PATH.open("r", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
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


def to_row(scenario: str, enabled: set[str], metrics: Metrics, baseline: Metrics) -> dict[str, str]:
    delta_auc = metrics.auc - baseline.auc
    delta_logloss = metrics.logloss - baseline.logloss
    delta_brier = metrics.brier - baseline.brier
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
        "decision": "基準" if scenario == "baseline_existing" else decide(delta_auc, delta_logloss),
    }


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    original_text = FEATURES_PATH.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []

    ensure_required_lines_present()
    ensure_baseline_feature_enabled()

    try:
        baseline_metrics: Metrics | None = None
        for scenario, enabled in SCENARIOS:
            apply_feature_states(enabled)
            metrics = run_metrics(scenario)
            if baseline_metrics is None:
                baseline_metrics = metrics
            rows.append(to_row(scenario, enabled, metrics, baseline_metrics))
            print(
                f"[{scenario}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, decision={rows[-1]['decision']}",
                flush=True,
            )
    finally:
        FEATURES_PATH.write_text(original_text, encoding="utf-8")

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
        "decision",
    ]
    with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    summary = {
        "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
        "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
        "rows": rows,
        "restored_features_state": "original features.yml restored",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
