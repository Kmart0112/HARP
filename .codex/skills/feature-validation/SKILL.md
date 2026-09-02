---
name: feature-validation
description: "Run unified feature adoption, hold, and reject workflows for candidate additions and existing-feature comparisons in this repository. Use when deciding whether to add a new feature, append improved-set experiments to the same MLflow theme, review evidence, and update `pipeline/config/feature_registry.yml` as the source of truth."
---

# Feature Validation

## Overview

Use this skill when the goal is to decide whether a feature or feature set should be adopted, held, or rejected.

This skill has two modes:

1. `candidate_addition`
   - Evaluate new or changed features before promotion into the active set.
   - Standard flow is `start -> append -> finalize/promotion`.
   - For now, agents should stop at `start` or `append`; closing the theme with `finalize` is a manual CLI operation.
2. `existing_comparison`
   - Compare already enabled features and decide keep/drop winners.
   - Use this only for existing ON features, not as the second half of candidate validation.

Treat MLflow as the formal evidence source.

- `1 parent run = 1 validation theme`
- `1 child run = 1 comparison scenario`
- Source of truth for active feature sets is `pipeline/config/feature_registry.yml`
- Validation itself must not mutate source `pipeline/config/feature_registry.yml`
- Append updates the same parent theme instead of creating a new rerun theme
- Final promotion happens only after reviewing the report and MLflow evidence
- `feature_validation_log.csv` is legacy history, not part of the standard flow

Run commands from the repository root in `bash`.

Use these command forms:

```bash
uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1 dbt ...
uv run python ...
```

If the task is only to rerun or maintain the metrics notebook, use `$lgbm-fuku-platt-metrics-modeling`.

`candidate_addition` is the primary path for this skill.  
`existing_comparison` remains a supported secondary mode for already enabled features and should use `run_feature_selection.py` together with `docs/operations/feature_selection_job_usage.md`.

Use this command form for `existing_comparison`:

```bash
uv run python pipeline/jobs/run_feature_selection.py --preset <preset_name>
```

## Data Reference

1. Refer to the EveryDB EDB2 manual for raw source data definitions when designing or validating feature logic: `https://everydb.iwinz.net/edb2_manual/`.
2. Resolve column semantics from source specs first, then implement transformations in dbt.

## Standard Workflow

1. Define the candidate feature and leakage boundary.
2. Implement the dbt change and propagate the column to `mart.m_train_race_horse_past5`.
3. Add or update the corresponding dbt model YAML and include clear descriptions for each added or changed feature column.
4. If the dbt change introduces a new mart column, add an entry to `pipeline/config/feature_registry.yml` before formal validation.
5. Register the new column as inventory only at first:
   - set `role` and `category`
   - keep it out of the active base set by leaving the target `set_status` unset or `off`
   - do not mix it into baseline automatically
6. Build or refresh the mart as needed, then refresh the analysis Parquet cache with `scripts/refresh_analysis_cache.sh`.
7. Create or extend a preset from `notebook/config/feature_validation_presets/template_feature_set.yml`.
8. For every newly added feature (`change_type: add`), prepare at least one SHAP-reviewed scenario so the candidate is always reviewed and appears in the final report.
9. If multiple related new features are added together, also prepare a scenario that enables that related set together and review SHAP dependence against the set via `comparison_features`.
10. `start` the theme with baseline and candidate単独 `single_add` scenarios:

```bash
uv run python pipeline/jobs/run_feature_validation.py --preset <preset_name>
```

11. Review the parent run, child runs, final report, and runs CSV in MLflow.
12. If the candidate looks promising, extend the same preset with improved-set scenarios such as `feature_set_add` or `replace_existing`.
13. `append` the improved-set scenarios to the same parent theme:

```bash
uv run python pipeline/jobs/run_feature_validation.py \
  --preset <same_preset_name> \
  --resume-parent-run-id <parent_run_id> \
  --only-scenarios <scenario1,scenario2> \
  --append-note "<why this append was added>"
```

14. When the theme is decision-complete, close it manually from the CLI instead of having the agent run `finalize`:

```bash
uv run python pipeline/jobs/run_feature_validation.py \
  --preset <same_preset_name> \
  --resume-parent-run-id <parent_run_id> \
  --finalize \
  --append-note "<final decision note>"
```

15. Agents should not run `--finalize` automatically in this repository unless the user explicitly asks for that CLI operation.
16. If the final decision is `採用`, update `pipeline/config/feature_registry.yml`:
   - promote the feature into the relevant `set_status`
   - keep rejected candidates `off` or unset
   - attach the validation report path under `reports` when appropriate
17. After promotion, use `pipeline/jobs/export_feature_contract.py` when the adopted registry state must be reflected into a concrete feature contract.
18. Use `pipeline/jobs/render_feature_set.py` only to confirm the rendered set matches the intended registry state.

Do not treat manual notebook execution or `feature_validation_log.csv` append as the standard operating path.
Manual notebook execution is not the standard operating path.
Also, do not have the agent close `feature_validation` themes by default; leave the final `--finalize` step to a human-triggered CLI run.

## Leakage Guardrails

1. Use only information available before the target race starts.
2. Do not use same-race outcomes (`rank`, payout-derived values, finishing-time-derived results from the target race).
3. Do not join any table keyed by post-race facts of the target race.
4. For rolling or aggregate features, aggregate strictly from past races only.
5. If uncertainty exists, prefer conservative exclusion and document the reason.

## Step 1: Feature Specification

1. State feature name, data source, and formula in one sentence.
2. State the as-of timestamp, meaning when the value becomes known.
3. Classify the feature as numeric or categorical and note the intended `role` / `category` in `pipeline/config/feature_registry.yml`.
4. List likely overlapping existing features to compare later.
5. Decide the validation theme name that will become the preset and MLflow parent run name.
6. Decide the required comparison matrix before writing the preset:
   - `baseline_existing`
   - one `single_add` scenario per candidate feature
   - one `feature_set_add` scenario that enables all candidate features together
   - one or more `replace_existing` scenarios that swap similar existing features with the candidate side

## Step 2: dbt Implementation

1. Add or update feature models under `dbt/harp/models/features/...`.
2. Propagate the new column through intermediate models if needed.
3. Ensure the final column exists in `dbt/harp/models/mart/m_train_race_horse_past5.sql`.
4. Add or update the corresponding dbt model YAML and include clear descriptions for each added or changed feature column.
5. If a new mart column was added, register it in `pipeline/config/feature_registry.yml` before validation:
   - create the feature entry
   - set `role` and `category`
   - keep the compared set entry absent or `off` until adoption is decided
6. Before the formal validation flow, run the standard refresh script:

```bash
scripts/refresh_analysis_cache.sh --full-refresh
```

7. Confirm the refresh passes and the column exists in `mart.m_train_race_horse_past5`.

If dbt was already run and only Parquet refresh is needed before validation:

```bash
scripts/refresh_analysis_cache.sh --skip-dbt
```

## Step 3: Prepare the Validation Preset

Treat `candidate_addition` as one theme that grows by scenario.

Recommended order:

1. `baseline_existing`
2. candidate単独 `single_add`
3. improved-set `feature_set_add`
4. optional `replace_existing`

Use the same `preset_name` while extending the `scenarios` block. Do not switch to `feature_selection` just to evaluate an improved candidate set.

1. Copy `notebook/config/feature_validation_presets/template_feature_set.yml`.
2. Set `validation.name`, `change_summary`, and `report` text for the current theme.
3. Define scenarios under `scenarios`.
4. Include the required minimum scenario set:
   - `baseline_existing`
   - one `single_add` scenario per candidate feature
   - one `feature_set_add` scenario for all candidate features together
   - one or more `replace_existing` scenarios for similar existing features
5. Prefer `feature_set` with `base_feature_set_name`, `include_features`, and `exclude_features`.
6. Use `toggles` only as a compatibility fallback.
7. Every newly added feature (`change_type: add`) must appear as `shap.candidate_feature` in at least one scenario.
8. When multiple related added features are evaluated together, include at least one scenario where the related set is simultaneously enabled and list the other related features under `shap.comparison_features`.
9. Final reports should retain SHAP findings for every newly added feature reviewed in the theme.
10. Before finalizing scenario definitions, inspect the base feature set in `pipeline/config/feature_registry.yml` and confirm whether the compared features are already `on` there.
11. If the base feature set does not already contain the compared feature, do not rely on `exclude_features` alone. Explicitly add the target feature via `include_features` (and `include_cat_features` when relevant) so the scenario actually changes the effective set.
12. When comparing multiple alternative representations of the same signal and none are in the base set, treat each scenario as an add-only variant built on the same base feature set.
13. Newly added mart columns should stay out of the baseline set until adoption is decided; compare them through preset diffs, not by pre-enabling them in the registry.

The preset YAML is the source of truth for the validation run shape.

## Step 4: Run Formal Validation

What the job does:

1. Starts one MLflow parent run for the theme.
2. Expands scenarios into child runs.
3. Generates per-scenario temporary feature configs.
4. Runs metrics and, when configured, SHAP in the same child run.
5. Writes a final Markdown report and runs CSV.
6. Logs formal evidence to MLflow.

The job must leave source `pipeline/config/feature_registry.yml` untouched during validation.

### Path / Append Rules

- Append reuses the parent theme's `report_out`, `runs_csv_out`, and `run_log_dir`.
- `--run-log-dir` on append does not override the parent theme path.
- Runtime artifacts should stay under one `outputs/...` tree for the same theme.

Final report expectations for the current HARP workflow:

1. For SHAP-reviewed scenarios, the final report embeds the candidate feature's dependence plot directly.
2. The copied image lives under the final report's sibling `_images/` folder.
3. The final report must record which related feature set was checked via `comparison_features` when applicable.
4. The final report should include `dependence の形の考察` as a Codex visual read based on the copied dependence PNG, not as a generic placeholder.
5. Comparison dependence and local cases remain in the dedicated SHAP report, not the final feature validation report.
6. The agent should open the copied dependence PNG under `_images/`, inspect the actual shape in Codex, and write the commentary as a clearly labeled note such as `Codex手動所見: ...`.
7. That manual note should stay grounded in the visible dependence shape and mention at least:
   - monotonic or non-monotonic behavior
   - threshold, plateau, or saturation points when visible
   - whether the colorized `comparison_features` appears aligned with or mixed into the candidate trend
   - whether the high-impact region looks broad or driven by sparse tail observations
8. Edit the final Markdown report directly instead of rerunning the whole validation job unless the underlying artifacts themselves changed.

## Step 5: Review MLflow and Report Outputs

Review these artifacts:

1. Final report under `notebook/report/features`.
2. Runs CSV under `notebook/report/results`.
3. Parent run and child runs in MLflow.
4. SHAP artifacts attached to the relevant child runs.

Minimum checks:

1. Parent run represents exactly one validation theme.
2. Child run names match the preset scenarios.
3. The required comparison scenarios are present:
   - `baseline_existing`
   - all per-candidate `single_add`
   - one `feature_set_add` for all candidates
   - the intended `replace_existing` scenarios
4. The final report includes `mlflow_experiment_name` and `mlflow_run_id`.
5. The adopted, held, and rejected features match the scenario evidence.
6. Each SHAP-reviewed new feature in the final report includes:
   - candidate dependence image embed
   - checked comparison feature set when applicable
   - `Codex手動所見` による `dependence の形の考察`
   - link to the detailed SHAP report
7. Confirm the final report text was manually updated from the copied `_images/` PNG and does not merely repeat a generic SHAP sentence.

### Standard SHAP Commentary Flow

Use this as the default flow for SHAP commentary in the final report.

1. Open the final report under `notebook/report/features/...`.
2. Locate each SHAP-reviewed feature block and identify the copied dependence image path under the sibling `_images/` directory.
3. View the PNG in Codex and inspect the visible pattern before editing any text.
4. Write or replace the existing `dependence の形の考察` line with a concise Japanese note labeled `Codex手動所見:`.
5. Keep the commentary specific to the plotted shape rather than generic SHAP boilerplate.
6. Tie the visual read back to the adoption question when possible, for example whether the candidate looks redundant to the comparison feature or appears to carry an additional regime signal.
7. Do not modify MLflow state or rerun validation just to add this manual interpretation.

## Standard Comparison Points

1. Leakage boundary
   - Confirm the feature is knowable before the target race starts.
2. Metrics improvement
   - Review `AUC`, `LogLoss`, and `Brier` against the baseline and improved-set scenarios.
3. Redundancy
   - Check whether the candidate only duplicates existing feature behavior.
4. SHAP
   - Treat SHAP as a mandatory review point for newly added features in this mode.
   - When multiple related features are added, confirm dependence against the related set via `comparison_features`.
   - Confirm candidate dependence image embedding, `Codex手動所見` による `dependence の形の考察`, and the detailed SHAP report link.
   - SHAP is optional in this mode when the task is `existing_comparison`.
5. Stability
   - Review whether the signal is plausible and stable enough for promotion.

## Step 6: Promote Adopted Features

Promotion happens after validation, not during it.

1. If the final decision is `採用`, update `pipeline/config/feature_registry.yml` to reflect the adopted feature set.
2. If the final decision is `保留` or `不採用`, do not promote the candidate into the active set.
3. Keep the final `set_status` values aligned with the adopted result described in the report.
4. For newly validated features, keep the initial inventory entry and only change the relevant `set_status` plus `reports`.

## Step 7: Confirm the Rendered Feature Set After Promotion

After updating `pipeline/config/feature_registry.yml`, confirm the rendered feature set matches the intended active set.

Example:

```bash
uv run python pipeline/jobs/render_feature_set.py \
  --feature-set place_v1 \
  --mode production \
  --stdout
```

Use this as a confirmation step only. The source of truth remains the registry, not the rendered YAML output.

## Output Requirements

1. Keep the final validation report in Japanese under `notebook/report/features`.
2. Treat MLflow as the formal execution record.
3. Treat the parent run ID as the evidence ID for Git-facing summaries.
4. Do not append to `feature_validation_log.csv` as part of the standard flow.

## Practical Notes

1. When DB output changed, run `scripts/refresh_analysis_cache.sh --full-refresh` before the formal validation flow.
2. When DB output did not change, rerun the formal validation job directly.
3. When dbt output is already up to date but the Parquet cache must be rebuilt, run `scripts/refresh_analysis_cache.sh --skip-dbt` first.
4. Prefer one preset per decision theme instead of ad hoc notebook command sequences.
5. If the user asks only for metrics notebook maintenance, use `$lgbm-fuku-platt-metrics-modeling` instead.

## Resources

1. Formal workflow reference:
   - `docs/operations/feature_validation_job_usage.md`
2. Metrics-only workflow:
   - `$lgbm-fuku-platt-metrics-modeling`
3. Existing feature comparison references remain available for future dedicated workflow design:
   - `scripts/judge_feature_selection.py`
   - `references/selection_rules.md`
   - `references/variant_map_schema.md`
