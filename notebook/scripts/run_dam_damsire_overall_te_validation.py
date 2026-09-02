from __future__ import annotations

import csv
import dataclasses
import itertools
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path

import lightgbm as lgb
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = PROJECT_ROOT / "apps" / "analysis"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from src.modeling.fuku_platt_metrics_flow import (  # noqa: E402
    FukuPlattMetricsConfig,
    _append_metrics_log,
    _set_global_seed,
    load_source_dataframe,
)
from harp.core.training import build_binary_dataset, train_binary_lgbm  # noqa: E402
from pipeline.runtime_settings import load_pipeline_runtime_config  # noqa: E402


FEATURES_PATH = PROJECT_ROOT / "notebook" / "config" / "features.yml"
MODEL_EVAL_LOG_PATH = PROJECT_ROOT / "notebook" / "prd" / "outputs" / "model_eval_log.csv"
TODAY = date.today().strftime("%Y%m%d")
RUNS_CSV_PATH = (
    PROJECT_ROOT
    / "notebook"
    / "report"
    / "results"
    / f"{TODAY}_dam_damsire_overall_te_runs.csv"
)
RUN_LOG_DIR = PROJECT_ROOT / "outputs" / f"dam_damsire_overall_te_logs_{TODAY}"

TARGET_FEATURES = [
    "dam_avg_place_rate_smooth",
    "dam_avg_pos4_agari_synergy",
    "damsire_avg_place_rate_smooth",
    "damsire_avg_pos4_agari_synergy",
]
_ON_FEATURE_PATTERN = re.compile(r"^\s*-\s*([A-Za-z0-9_].*?)\s*$")


@dataclasses.dataclass
class Metrics:
    timestamp: str
    auc: float
    logloss: float
    brier: float
    feature_count: int


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


def resolve_feature_lists_from_config(drop_win_odds_features: bool = True) -> tuple[list[str], list[str], list[str]]:
    section: str | None = None
    feature_names: list[str] = []
    cat_features: list[str] = []

    for raw_line in FEATURES_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped == "feature_names:":
            section = "feature_names"
            continue
        if stripped == "cat_features:":
            section = "cat_features"
            continue
        if section is None:
            continue

        on_match = _ON_FEATURE_PATTERN.match(raw_line)
        if on_match is None:
            continue

        feature = on_match.group(1).strip()
        if section == "feature_names":
            feature_names.append(feature)
        elif section == "cat_features":
            cat_features.append(feature)

    if not feature_names:
        raise ValueError(f"feature_names is empty: {FEATURES_PATH}")

    feature_set = set(feature_names)
    missing_cat = [feature for feature in cat_features if feature not in feature_set]
    if missing_cat:
        raise ValueError(f"cat_features not present in feature_names: {missing_cat}")

    num_features = [feature for feature in feature_names if feature not in set(cat_features)]
    if drop_win_odds_features:
        num_features = [feature for feature in num_features if feature not in {"j_odds_tansho", "log_odds_tansho"}]

    return feature_names, num_features, cat_features


def read_latest_metrics() -> Metrics:
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
        feature_count=0,
    )


def build_config() -> FukuPlattMetricsConfig:
    runtime_config = load_pipeline_runtime_config()
    return FukuPlattMetricsConfig(
        train_year_start=2013,
        train_year_end=2024,
        test_year=2025,
        fukusho_type="j_odds_fukusho_avg",
        global_seed=42,
        use_cache=True,
        refresh_cache=False,
        cache_dir=PROJECT_ROOT / "notebook" / "prd" / "tmp" / "analysis_cache",
        output_log_path=MODEL_EVAL_LOG_PATH,
        db_url=runtime_config.database.db_url,
        query_chunk_size=200_000,
        drop_win_odds_features=True,
    )


def run_metrics(run_name: str, cfg: FukuPlattMetricsConfig, df) -> Metrics:
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    before = read_latest_metrics().timestamp if MODEL_EVAL_LOG_PATH.exists() else ""
    log_path = RUN_LOG_DIR / f"{run_name}.log"
    buffer = StringIO()

    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            _set_global_seed(cfg.global_seed)
            feature_names, num_features, cat_features = resolve_feature_lists_from_config(cfg.drop_win_odds_features)
            ds = build_binary_dataset(
                df=df,
                feature_names=feature_names,
                cat_features=cat_features,
                target_col="is_place",
                train_year_start=cfg.train_year_start,
                train_year_end=cfg.train_year_end,
                test_year=cfg.test_year,
            )
            model_params = {
                "objective": "binary",
                "n_estimators": 4000,
                "learning_rate": 0.03,
                "num_leaves": 15,
                "max_depth": 4,
                "subsample": 0.8,
                "colsample_bytree": 0.6,
                "min_child_samples": 200,
                "min_split_gain": 0.01,
                "reg_alpha": 0.0,
                "reg_lambda": 0.0,
                "random_state": cfg.global_seed,
                "bagging_seed": cfg.global_seed,
                "feature_fraction_seed": cfg.global_seed,
                "data_random_seed": cfg.global_seed,
                "n_jobs": 6,
            }
            fit_kwargs = {
                "eval_set": [(ds.X_val, ds.y_val)],
                "eval_metric": "binary_logloss",
                "callbacks": [
                    lgb.early_stopping(200, verbose=True),
                    lgb.log_evaluation(period=50),
                ],
            }
            result = train_binary_lgbm(
                ds=ds,
                model_params=model_params,
                fit_kwargs=fit_kwargs,
            )
            metrics = result.metrics
            y_pred_proba = result.model.predict_proba(ds.X_test)[:, 1]
            auc = float(roc_auc_score(ds.y_test, y_pred_proba))
            brier = float(brier_score_loss(ds.y_test, y_pred_proba))
            logloss_value = float(log_loss(ds.y_test, y_pred_proba))
            _append_metrics_log(
                cfg=cfg,
                model=result.model,
                auc=auc,
                brier=brier,
                logloss_value=logloss_value,
                n_test=len(ds.y_test),
            )
    except Exception:
        log_path.write_text(buffer.getvalue(), encoding="utf-8")
        raise

    log_path.write_text(buffer.getvalue(), encoding="utf-8")
    after = read_latest_metrics()
    if before and after.timestamp == before:
        raise RuntimeError(f"model_eval_log not updated for run: {run_name}")
    return Metrics(
        timestamp=after.timestamp,
        auc=auc,
        logloss=logloss_value,
        brier=brier,
        feature_count=len(ds.feature_names),
    )


def _scenario_name(enabled: tuple[str, ...]) -> str:
    if not enabled:
        return "baseline"
    return "addon__" + "__".join(enabled)


def _row(enabled: tuple[str, ...], metrics: Metrics, baseline: Metrics) -> dict[str, str]:
    delta_auc = metrics.auc - baseline.auc
    delta_logloss = metrics.logloss - baseline.logloss
    delta_brier = metrics.brier - baseline.brier
    return {
        "scenario": _scenario_name(enabled),
        "enabled_features": "|".join(enabled),
        "timestamp": metrics.timestamp,
        "auc": f"{metrics.auc:.9f}",
        "logloss": f"{metrics.logloss:.9f}",
        "brier": f"{metrics.brier:.9f}",
        "delta_auc": f"{delta_auc:+.9f}",
        "delta_logloss": f"{delta_logloss:+.9f}",
        "delta_brier": f"{delta_brier:+.9f}",
        "feature_count": str(metrics.feature_count),
        "improved": "yes" if delta_auc > 0 and delta_logloss < 0 else "no",
    }


def _feature_count(row: dict[str, str]) -> int:
    enabled = row["enabled_features"]
    return 0 if not enabled else len(enabled.split("|"))


def _best_row(rows: list[dict[str, str]]) -> dict[str, str] | None:
    improved_rows = [row for row in rows if row["scenario"] != "baseline" and row["improved"] == "yes"]
    if not improved_rows:
        return None
    return max(
        improved_rows,
        key=lambda row: (
            float(row["delta_auc"]),
            -float(row["delta_logloss"]),
            -_feature_count(row),
        ),
    )


def main() -> None:
    RUNS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    original_features_text = FEATURES_PATH.read_text(encoding="utf-8")
    success = False

    try:
        cfg = build_config()
        df = load_source_dataframe(cfg)
        rows: list[dict[str, str]] = []
        scenarios = [()]
        for subset_size in range(1, len(TARGET_FEATURES) + 1):
            scenarios.extend(itertools.combinations(TARGET_FEATURES, subset_size))

        baseline_metrics: Metrics | None = None
        for enabled in scenarios:
            enabled_set = set(enabled)
            apply_feature_states(enabled_set)
            metrics = run_metrics(_scenario_name(enabled), cfg, df)
            if baseline_metrics is None:
                baseline_metrics = metrics
            row = _row(enabled, metrics, baseline_metrics)
            rows.append(row)
            print(
                f"[{row['scenario']}] auc={metrics.auc:.9f}, logloss={metrics.logloss:.9f}, improved={row['improved']}",
                flush=True,
            )

        best_row = _best_row(rows)
        adopted = set(best_row["enabled_features"].split("|")) if best_row and best_row["enabled_features"] else set()
        apply_feature_states(adopted)

        headers = [
            "scenario",
            "enabled_features",
            "timestamp",
            "auc",
            "logloss",
            "brier",
            "feature_count",
            "delta_auc",
            "delta_logloss",
            "delta_brier",
            "improved",
        ]
        with RUNS_CSV_PATH.open("w", encoding="utf-8", newline="") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        summary = {
            "runs_csv": str(RUNS_CSV_PATH.relative_to(PROJECT_ROOT)),
            "run_log_dir": str(RUN_LOG_DIR.relative_to(PROJECT_ROOT)),
            "best_scenario": None if best_row is None else best_row["scenario"],
            "best_feature_set": None if best_row is None else best_row["enabled_features"],
            "decision": "不採用" if best_row is None else "採用",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        success = True
    finally:
        if not success:
            FEATURES_PATH.write_text(original_features_text, encoding="utf-8")


if __name__ == "__main__":
    main()
