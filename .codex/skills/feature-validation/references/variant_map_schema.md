# Variant Map Schema

## Purpose

Define explicit same-scale comparison groups for variant selection.

## Required Structure

```yaml
run_name: "<string>"
variant_groups:
  - group_id: "<string>"
    candidates:
      - "<feature_name>"
      - "<feature_name>"
    selection_mode: "tournament_one_winner"
```

## Field Rules

1. `run_name`:
   - Non-empty string.
   - Use a stable identifier for report titles and output tracking.
2. `variant_groups`:
   - Non-empty list.
3. `group_id`:
   - Unique string within the file.
4. `candidates`:
   - 2 or more feature names.
   - Use names exactly as they appear in ablation output `tested_set`.
5. `selection_mode`:
   - Must be `tournament_one_winner`.

## Example

```yaml
run_name: "202602XX_feature_validation_existing_comparison"
variant_groups:
  - group_id: "time_vs_avg_family"
    candidates:
      - "time_vs_avg_wavg5_recent"
      - "time_vs_avg_avg5"
      - "time_vs_avg_avg3"
    selection_mode: "tournament_one_winner"

  - group_id: "sire_place_rate_family"
    candidates:
      - "same_cluster_sire_avg_place_rate_smooth"
      - "same_surface_dist_pm200_sire_avg_place_rate"
    selection_mode: "tournament_one_winner"
```

## Notes

1. Keep this mapping explicit even when naming patterns are obvious.
2. Do not include `_z` or `_rank` variants in same-scale groups.
3. If a candidate is missing from result CSV, mark the group unresolved instead of forcing a winner.
