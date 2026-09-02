{{ config(
  materialized='incremental',
  unique_key=['kettonum', 'jockey_cd', 'held_date'],
  tags=['feature'],
  indexes=[
    {'columns': ['kettonum', 'jockey_cd', 'held_date']}
  ]
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }}
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date
  {% endif %}
),

pair_condition_metrics as (
  select
    *
  from {{ ref('int_jockey_horse_pair_condition_daily_cum_long') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
)

select
  kettonum,
  jockey_cd,
  held_date,
  max(
    case
      when condition_group = 'overall' then weighted_avg_pos4_agari_synergy
    end
  ) as jockey_horse_pair_weighted_avg_pos4_agari_synergy,
  max(
    case
      when condition_group = 'course_cluster' then weighted_avg_pos4_agari_synergy
    end
  ) as jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
  max(
    case
      when condition_group = 'turn_direction_surface' then weighted_avg_pos4_agari_synergy
    end
  ) as jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy
from pair_condition_metrics
group by
  kettonum,
  jockey_cd,
  held_date
