{{ config(
  materialized='incremental',
  unique_key=['damsire_id', 'held_year_month'],
  indexes=[{'columns': ['damsire_id', 'held_year_month']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    damsire_id,
    held_year_month,
    is_place,
    is_win,
    pos4_agari_synergy,
    time_diff
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and damsire_id is not null
    and damsire_id <> 0
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_damsire as (
  select
    damsire_id,
    held_year_month,
    count(*) as starts,
    sum(is_place) as places,
    sum(is_win) as wins,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count,
    sum(time_diff) as time_diff_sum,
    count(time_diff) as time_diff_count
  from base
  group by
    damsire_id,
    held_year_month
),

yearly_damsire_roll as (
  select
    yd.*,
    sum(yd.starts) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_starts_5y,
    sum(yd.places) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_places_5y,
    sum(yd.wins) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_wins_5y,
    sum(yd.pos4_agari_synergy_sum) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_pos4_agari_synergy_sum_5y,
    sum(yd.pos4_agari_synergy_count) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_pos4_agari_synergy_count_5y,
    sum(yd.time_diff_sum) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_time_diff_sum_5y,
    sum(yd.time_diff_count) over (
      partition by yd.damsire_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as damsire_time_diff_count_5y
  from yearly_damsire yd
)

select
  damsire_id,
  held_year_month,
  damsire_starts_5y,
  damsire_places_5y,
  damsire_places_5y / nullif(damsire_starts_5y, 0) as damsire_avg_place_rate,
  ((damsire_places_5y + (0.213 * 50))::float
    / nullif(damsire_starts_5y + 50, 0)) as damsire_avg_place_rate_smooth,
  damsire_pos4_agari_synergy_sum_5y::float
    / nullif(damsire_pos4_agari_synergy_count_5y, 0) as damsire_avg_pos4_agari_synergy,
  damsire_time_diff_sum_5y::float
    / nullif(damsire_time_diff_count_5y, 0) as damsire_avg_time_diff
from yearly_damsire_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
