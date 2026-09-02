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
    / f"{TODAY}_sire_conditional_pos4_vs_place_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"sire_conditional_pos4_logs_{TODAY}"

CONDITIONAL_PLACE = {
    "cluster": "same_cluster_sire_avg_place_rate_smooth",
    "surface_dist_pm200": "same_surface_dist_pm200_sire_avg_place_rate",
    "age": "same_age_sire_avg_place_rate_smooth_prev_age",
}
CONDITIONAL_POS4 = {
    "cluster": "same_cluster_sire_avg_pos4_agari_synergy",
    "surface_dist_pm200": "same_surface_dist_pm200_sire_avg_pos4_agari_synergy",
    "age": "same_age_sire_avg_pos4_agari_synergy",
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


def apply_feature_states(enabled: set[str]) -> None:
    text = FEATURES_PATH.read_text(encoding="utf-8")
    for feature in set(CONDITIONAL_PLACE.values()).union(CONDITIONAL_POS4.values()):
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
    mode: str,
    scenario: str,
    enabled: set[str],
    metrics: Metrics,
    base: Metrics,
    group: str = "",
    compare_target: str = "",
) -> dict[str, str]:
    return {
        "mode": mode,
        "group": group,
        "scenario": scenario,
        "compare_target": compare_target,
        "enabled_features": "|".join(sorted(enabled)),
        "timestamp": metrics.timestamp,
        "auc": f"{metrics.auc:.9f}",
        "logloss": f"{metrics.logloss:.9f}",
        "brier": f"{metrics.brier:.9f}",
        "delta_auc": f"{metrics.auc - base.auc:+.9f}",
        "delta_logloss": f"{metrics.logloss - base.logloss:+.9f}",
        "delta_brier": f"{metrics.brier - base.brier:+.9f}",
    }


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []

    none_enabled: set[str] = set()
    place_all = set(CONDITIONAL_PLACE.values())
    pos4_all = set(CONDITIONAL_POS4.values())

    # 1) Mandatory single comparison: place-rate single vs avg_pos4 single
    apply_feature_states(none_enabled)
    single_base_metrics = run_metrics("single_base_no_conditional")
    rows.append(
        _row(
            mode="single_compare",
            scenario="single_base_no_conditional",
            enabled=none_enabled,
            metrics=single_base_metrics,
            base=single_base_metrics,
        )
    )
    print(
        f"[single] base: auc={single_base_metrics.auc:.9f}, logloss={single_base_metrics.logloss:.9f}",
        flush=True,
    )

    for group in ("cluster", "surface_dist_pm200", "age"):
        place_feat = CONDITIONAL_PLACE[group]
        pos4_feat = CONDITIONAL_POS4[group]

        apply_feature_states({place_feat})
        place_metrics = run_metrics(f"single_{group}_place")
        rows.append(
            _row(
                mode="single_compare",
                scenario=f"single_{group}_place",
                enabled={place_feat},
                metrics=place_metrics,
                base=single_base_metrics,
                group=group,
                compare_target=place_feat,
            )
        )
        print(
            f"[single] {group} place: auc={place_metrics.auc:.9f}, logloss={place_metrics.logloss:.9f}",
            flush=True,
        )

        apply_feature_states({pos4_feat})
        pos4_metrics = run_metrics(f"single_{group}_pos4")
        rows.append(
            _row(
                mode="single_compare",
                scenario=f"single_{group}_pos4",
                enabled={pos4_feat},
                metrics=pos4_metrics,
                base=single_base_metrics,
                group=group,
                compare_target=pos4_feat,
            )
        )
        print(
            f"[single] {group} pos4: auc={pos4_metrics.auc:.9f}, logloss={pos4_metrics.logloss:.9f}",
            flush=True,
        )

    # 2) Add-on comparison on current formal place-rate set
    apply_feature_states(place_all)
    add_base_metrics = run_metrics("addon_base_place_all")
    rows.append(
        _row(
            mode="add_on",
            scenario="addon_base_place_all",
            enabled=place_all,
            metrics=add_base_metrics,
            base=add_base_metrics,
        )
    )
    print(f"[add_on] base(place_all): auc={add_base_metrics.auc:.9f}, logloss={add_base_metrics.logloss:.9f}", flush=True)

    for group in ("cluster", "surface_dist_pm200", "age"):
        pos4_feat = CONDITIONAL_POS4[group]
        enabled = set(place_all)
        enabled.add(pos4_feat)
        apply_feature_states(enabled)
        metrics = run_metrics(f"addon_{group}_pos4")
        rows.append(
            _row(
                mode="add_on",
                scenario=f"addon_{group}_pos4",
                enabled=enabled,
                metrics=metrics,
                base=add_base_metrics,
                group=group,
                compare_target=pos4_feat,
            )
        )
        print(f"[add_on] {group} pos4: auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}", flush=True)

    enabled = place_all.union(pos4_all)
    apply_feature_states(enabled)
    metrics_all = run_metrics("addon_all_pos4")
    rows.append(
        _row(
            mode="add_on",
            scenario="addon_all_pos4",
            enabled=enabled,
            metrics=metrics_all,
            base=add_base_metrics,
        )
    )
    print(f"[add_on] all pos4: auc={metrics_all.auc:.9f}, logloss={metrics_all.logloss:.9f}", flush=True)

    # Restore current formal: place-rate conditionals ON, pos4 conditionals OFF
    apply_feature_states(place_all)

    headers = [
        "mode",
        "group",
        "scenario",
        "compare_target",
        "enabled_features",
        "timestamp",
        "auc",
        "logloss",
        "brier",
        "delta_auc",
        "delta_logloss",
        "delta_brier",
    ]
    with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    # Pairwise winner for mandatory single comparison
    winners: dict[str, str] = {}
    for group in ("cluster", "surface_dist_pm200", "age"):
        place_row = next(r for r in rows if r["scenario"] == f"single_{group}_place")
        pos4_row = next(r for r in rows if r["scenario"] == f"single_{group}_pos4")
        place_ok = float(place_row["delta_auc"]) > 0 and float(place_row["delta_logloss"]) < 0
        pos4_ok = float(pos4_row["delta_auc"]) > 0 and float(pos4_row["delta_logloss"]) < 0
        if place_ok and not pos4_ok:
            winners[group] = "place"
        elif pos4_ok and not place_ok:
            winners[group] = "pos4"
        elif place_ok and pos4_ok:
            winners[group] = (
                "pos4"
                if (
                    float(pos4_row["delta_auc"]) > float(place_row["delta_auc"])
                    or (
                        float(pos4_row["delta_auc"]) == float(place_row["delta_auc"])
                        and float(pos4_row["delta_logloss"]) < float(place_row["delta_logloss"])
                    )
                )
                else "place"
            )
        else:
            winners[group] = "neither"

    summary = {
        "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
        "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
        "single_compare_winner_by_group": winners,
        "addon_all_pos4_delta_auc": rows[-1]["delta_auc"],
        "addon_all_pos4_delta_logloss": rows[-1]["delta_logloss"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
