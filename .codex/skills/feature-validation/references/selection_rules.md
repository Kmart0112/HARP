# Selection Rules

## Scope

1. Evaluate only currently enabled features in `pipeline/config/feature_registry.yml` for the target feature set.
2. Use `notebook/prd/lgbm_fuku_platt_metrics.py` as the metrics runner.
3. Keep workflow reproducible with fixed thresholds and fixed ordering.

## Global Threshold

Use:

- `delta_auc > 1e-5`
- `delta_logloss < -1e-5`

Treat this as a strict AND condition for "improved".

## Rule Order

1. Run aggregate three-way comparison first.
2. Run same-scale variant comparison second.
3. Reflect winners/losers in `pipeline/config/feature_registry.yml` by updating `set_status` for the target set.

## Aggregate Three-Way Rule

For each `group_id`, compare:

- `aggregate_only`
- `source_only`
- `all_features`

Selection policy:

1. Prefer improved candidates (global threshold).
2. If no candidate improves globally, keep relative best by metrics.
3. If top candidates are within threshold-difference tie:
   - Prefer simpler set in this order:
   - `aggregate_only` > `source_only` > `all_features`

## Aggregate Source Approximation (Naming Rule)

When preparing aggregate groups, approximate source-family mapping with name tokens:

- `avg`
- `wavg`
- `weighted`
- `smooth`
- `place_rate`

Exclude `_z` and `_rank` from same-scale comparisons.

If source approximation is ambiguous or incomplete, mark the group as `unresolved` and do not force drop.

## Variant Comparison Rule

Use the explicit variant map YAML (no implicit grouping).

1. Evaluate only mapped candidates in each variant group.
2. If one or more candidates improve, keep exactly one winner.
3. If multiple improved candidates exist, tie-break by:
   - `AUC` (higher better)
   - `LogLoss` (lower better)
   - `Brier` (lower better)
4. If none improves, return `current_keep`.

For groups with 3+ candidates, resolve one winner (tournament one winner).

## Output Contract

Decision CSV required columns:

- `group_id`
- `decision_type`
- `winner_set`
- `loser_sets`
- `reason`
- `delta_auc`
- `delta_logloss`
- `delta_brier`

Report output:

1. Write in Japanese.
2. Include applied thresholds.
3. Include aggregate decisions table.
4. Include variant decisions table.
5. Include unresolved groups section.
