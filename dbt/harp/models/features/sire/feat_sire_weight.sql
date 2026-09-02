{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'h_weight_bin'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'h_weight_bin']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    sire_id,
    held_year_month,
    is_place,
    is_win,
    h_weight_bin
  from {{ ref('int_race_entry_enriched') }}
  where held_year_month is not null
    and sire_id is not null
    and h_weight_bin is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_sire_weight as (
  select
    sire_id,
    held_year_month,
    h_weight_bin,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins
  from base
  group by
    sire_id,
    held_year_month,
    h_weight_bin
),

yearly_sire_weight_roll as (
  select
    ysw.*,
    sum(ysw.starts) over (
      partition by ysw.sire_id, ysw.h_weight_bin
      order by ysw.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_weight_sire_starts_5y,
    sum(ysw.places) over (
      partition by ysw.sire_id, ysw.h_weight_bin
      order by ysw.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_weight_sire_places_5y,
    sum(ysw.wins) over (
      partition by ysw.sire_id, ysw.h_weight_bin
      order by ysw.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_weight_sire_wins_5y
  from yearly_sire_weight ysw
)

select
  sire_id,
  held_year_month,
  h_weight_bin,
  same_weight_sire_starts_5y,
  same_weight_sire_places_5y,
  same_weight_sire_wins_5y,
  same_weight_sire_places_5y::float / nullif(same_weight_sire_starts_5y, 0) as same_weight_sire_place_rate_5y
from yearly_sire_weight_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
