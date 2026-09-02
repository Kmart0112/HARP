---
name: lgbm-fuku-platt-metrics-modeling
description: Run and maintain the LightGBM place-probability metrics workflow through script-mode notebook `notebook/prd/lgbm_fuku_platt_metrics.py` with feature config in `notebook/config/features.yml`. Use when creating, rerunning, or modifying the fukusho metrics experiment, including DB/cache refresh decisions after dbt changes. In formal feature validation, treat `pipeline/config/feature_registry.yml` as the source of truth.
---

# LGBM Fuku Platt Metrics Modeling

## Overview

Run the metrics workflow through script-mode notebook execution, not by manually executing cells.

Run commands from the repository root in `bash`.

Use these command forms:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt ...
uv run --isolated --frozen python ...
```

## Entry Point

Use:

```bash
uv run python notebook/prd/lgbm_fuku_platt_metrics.py
```

Set `HARP_DB_URL` in the local `.env` file before execution. Do not place credentials directly in commands or committed files.

Default behavior:

1. Query PostgreSQL `mart.m_train_race_horse_past5` (race_level 1-3, held_date filter).
2. Load feature lists from `notebook/config/features.yml`.
3. Build year-based split (`train`, `val`, `test`) through `build_binary_dataset`.
4. Train LightGBM with fixed notebook-compatible params.
5. Evaluate AUC/Brier/LogLoss on test split.
6. Append metrics to `notebook/prd/outputs/model_eval_log.csv`.
7. Save canonical artifact/manifest to `notebook/prd/outputs/artifacts/is_place_notebook_v1.pkl` and `notebook/prd/outputs/metadata/is_place_notebook_v1.json`.

Execution note:
- Script/CUI実行時は notebook 側設定 `read_from_db_default=False` が使われる（キャッシュ優先固定）。
- DB再読込や cache 再生成が必要な場合は、先に `scripts/refresh_analysis_cache.sh` を実行する。

## DB Change Decision

### Case A: DB or dbt model changed

Examples: `dbt/harp/models/...` changed, `mart.m_train_race_horse_past5` rebuilt, feature SQL updated.

1. Refresh dbt output and the standard analysis Parquet cache:

```bash
scripts/refresh_analysis_cache.sh --full-refresh
```

2. Run the metrics notebook:

```bash
uv run python notebook/prd/lgbm_fuku_platt_metrics.py
```

Rationale: rebuild dbt output first, then refresh the Parquet cache that the notebook reuses.

### Case B: DB unchanged (code-only rerun or repeated evaluation)

Use cached data for faster iteration (default behavior):

```bash
uv run python notebook/prd/lgbm_fuku_platt_metrics.py
```

If cache does not exist yet, run once (it will be created under `notebook/tmp/analysis_cache`).

## Common Options

```bash
HARP_ENV=dev uv run python notebook/prd/lgbm_fuku_platt_metrics.py
```

The example above loads `.env.dev`; keep the real database URL only in that ignored local file.

Tune parameters by editing the constants and UI cells in `notebook/prd/lgbm_fuku_platt_metrics.py`.

## Guardrails

1. Keep split policy fixed for comparability (`train_year_start`, `train_year_end`, `test_year`).
2. Keep deterministic seed fields aligned (global seed and LightGBM seed params).
3. If `KeyError: ... not in index` occurs, treat as feature/DB schema drift:
   - Rebuild mart and refresh Parquet with `scripts/refresh_analysis_cache.sh --full-refresh`.
   - Or adjust `notebook/config/features.yml` to valid columns.
4. Keep `categorical_feature=cat_features` in training.
5. If `OSError: libgomp.so.1` occurs, the runtime is missing a system dependency for LightGBM:
   - Use an environment/container where `libgomp` is available, then rerun the same command.
   - If isolated mode is blocked locally, use the project fallback command form (`UV_PROJECT_ENVIRONMENT=.venv-wsl uv run --no-sync python ...`).

## Expected Output

Console metrics plus updated log file:

- `notebook/prd/outputs/model_eval_log.csv`

## Relation To Feature Validation

When this notebook is run as part of formal feature validation, treat the MLflow parent run, child runs, final report, and runs CSV as the evidence set.

In that formal validation path:

1. `pipeline/config/feature_registry.yml` is the source of truth for active feature sets.
2. The validation job resolves the selected set from the registry and passes a temporary rendered YAML into the notebook runner.
3. If dbt introduces a new mart column, register it in the registry before running formal validation.
4. Keep the new column out of the active base set until adoption is decided.

Do not append to `notebook/report/results/feature_validation_log.csv` as part of the standard flow. That file is legacy history only.
