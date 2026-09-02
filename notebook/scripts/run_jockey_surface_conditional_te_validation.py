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
    / f"{TODAY}_jockey_surface_conditional_te_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"jockey_surface_conditional_te_logs_{TODAY}"

FORMAL_JOCKEY_BASE_FEATURES = {
    "jockey_avg_place_rate_smooth",
    "jockey_cluster_avg_place_rate_corrected",
    "jockey_style_place_rate_3y_smooth",
}

DISTANCE_EXACT_FEATURE = "jockey_surface_distance_place_rate_3y_smooth"
DISTANCE_PM200_FEATURE = "jockey_surface_dist_pm200_place_rate_3y_smooth"
JYO_FEATURE = "jockey_surface_jyo_place_rate_3y_smooth"
STYLE_FEATURE = "jockey_surface_style_place_rate_3y_smooth"

CANDIDATE_FEATURES = {
    DISTANCE_EXACT_FEATURE,
    DISTANCE_PM200_FEATURE,
    JYO_FEATURE,
    STYLE_FEATURE,
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


def assert_formal_jockey_base_features_enabled() -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    missing = [feature for feature in sorted(FORMAL_JOCKEY_BASE_FEATURES) if not _is_feature_enabled(text, feature)]
    if missing:
        raise ValueError(f"formal jockey base feature is OFF in features.yml: {missing}")


def apply_candidate_feature_states(enabled: set[str]) -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    for feature in CANDIDATE_FEATURES:
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
) -> dict[str, str]:
    delta_auc = metrics.auc - base.auc
    delta_logloss = metrics.logloss - base.logloss
    delta_brier = metrics.brier - base.brier
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
        "improved": "yes" if delta_auc > 0 and delta_logloss < 0 else "no",
    }


def _is_improved(row: dict[str, str]) -> bool:
    return float(row["delta_auc"]) > 0 and float(row["delta_logloss"]) < 0


def _choose_distance_winner(rows: dict[str, dict[str, str]], scenarios: dict[str, set[str]]) -> tuple[str, set[str]]:
    candidates = []
    for scenario in ("add_surface_distance_exact", "add_surface_distance_pm200", "add_surface_distance_both"):
        row = rows[scenario]
        if not _is_improved(row):
            continue
        candidates.append(
            (
                float(row["delta_auc"]),
                -float(row["delta_logloss"]),
                -len(scenarios[scenario]),
                scenario,
            )
        )
    if not candidates:
        return "none", set()
    winner = max(candidates)[3]
    return winner, set(scenarios[winner])


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    original_features_text = FEATURES_PATH.read_text(encoding="utf-8")
    success = False

    try:
        assert_formal_jockey_base_features_enabled()

        scenario_features: dict[str, set[str]] = {
            "base_formal": set(),
            "add_surface_distance_exact": {DISTANCE_EXACT_FEATURE},
            "add_surface_distance_pm200": {DISTANCE_PM200_FEATURE},
            "add_surface_jyo": {JYO_FEATURE},
            "add_surface_style": {STYLE_FEATURE},
            "add_surface_distance_both": {DISTANCE_EXACT_FEATURE, DISTANCE_PM200_FEATURE},
        }

        ordered_scenarios = [
            "base_formal",
            "add_surface_distance_exact",
            "add_surface_distance_pm200",
            "add_surface_jyo",
            "add_surface_style",
            "add_surface_distance_both",
        ]

        rows: list[dict[str, str]] = []
        row_by_scenario: dict[str, dict[str, str]] = {}

        apply_candidate_feature_states(set())
        base_metrics = run_metrics("base_formal")
        base_row = _row("base_formal", set(), base_metrics, base_metrics)
        rows.append(base_row)
        row_by_scenario["base_formal"] = base_row
        print(
            f"[base_formal] auc={base_metrics.auc:.9f}, logloss={base_metrics.logloss:.9f}",
            flush=True,
        )

        for scenario in ordered_scenarios[1:]:
            enabled = scenario_features[scenario]
            apply_candidate_feature_states(enabled)
            metrics = run_metrics(scenario)
            row = _row(scenario, enabled, metrics, base_metrics)
            rows.append(row)
            row_by_scenario[scenario] = row
            print(
                f"[{scenario}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, improved={row['improved']}",
                flush=True,
            )

        distance_winner_scenario, distance_winner_features = _choose_distance_winner(
            rows=row_by_scenario,
            scenarios=scenario_features,
        )

        scenario_features["add_best_distance_plus_jyo"] = set(distance_winner_features).union({JYO_FEATURE})
        scenario_features["add_best_distance_plus_style"] = set(distance_winner_features).union({STYLE_FEATURE})
        scenario_features["add_best_distance_plus_jyo_plus_style"] = set(distance_winner_features).union(
            {JYO_FEATURE, STYLE_FEATURE}
        )

        for scenario in (
            "add_best_distance_plus_jyo",
            "add_best_distance_plus_style",
            "add_best_distance_plus_jyo_plus_style",
        ):
            enabled = scenario_features[scenario]
            apply_candidate_feature_states(enabled)
            metrics = run_metrics(scenario)
            row = _row(scenario, enabled, metrics, base_metrics)
            rows.append(row)
            row_by_scenario[scenario] = row
            print(
                f"[{scenario}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, improved={row['improved']}",
                flush=True,
            )

        adopted_features = set(distance_winner_features)
        if _is_improved(row_by_scenario["add_surface_jyo"]):
            adopted_features.add(JYO_FEATURE)
        if _is_improved(row_by_scenario["add_surface_style"]):
            adopted_features.add(STYLE_FEATURE)

        apply_candidate_feature_states(adopted_features)

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
            "improved",
        ]
        with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        summary = {
            "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
            "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
            "distance_winner_scenario": distance_winner_scenario,
            "distance_winner_features": sorted(distance_winner_features),
            "adopted_features": sorted(adopted_features),
            "formal_jockey_base_features": sorted(FORMAL_JOCKEY_BASE_FEATURES),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        success = True
    finally:
        if not success:
            FEATURES_PATH.write_text(original_features_text, encoding="utf-8")


if __name__ == "__main__":
    main()
