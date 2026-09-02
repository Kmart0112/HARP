{{ config(
  materialized='incremental',
  unique_key=['dam_id', 'held_year_month'],
  indexes=[{'columns': ['dam_id', 'held_year_month']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    dam_id,
    held_year_month,
    is_place,
    is_win,
    pos4_agari_synergy,
    time_diff
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and dam_id is not null
    and dam_id <> 0
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_dam as (
  select
    dam_id,
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
    dam_id,
    held_year_month
),

yearly_dam_roll as (
  select
    yd.*,
    sum(yd.starts) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_starts_5y,
    sum(yd.places) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_places_5y,
    sum(yd.wins) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_wins_5y,
    sum(yd.pos4_agari_synergy_sum) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_pos4_agari_synergy_sum_5y,
    sum(yd.pos4_agari_synergy_count) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_pos4_agari_synergy_count_5y,
    sum(yd.time_diff_sum) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_time_diff_sum_5y,
    sum(yd.time_diff_count) over (
      partition by yd.dam_id
      order by yd.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as dam_time_diff_count_5y
  from yearly_dam yd
)

select
  dam_id,
  held_year_month,
  dam_starts_5y,
  dam_places_5y,
  dam_places_5y / nullif(dam_starts_5y, 0) as dam_avg_place_rate,
  ((dam_places_5y + (0.213 * 50))::float
    / nullif(dam_starts_5y + 50, 0)) as dam_avg_place_rate_smooth,
  dam_pos4_agari_synergy_sum_5y::float
    / nullif(dam_pos4_agari_synergy_count_5y, 0) as dam_avg_pos4_agari_synergy,
  dam_time_diff_sum_5y::float
    / nullif(dam_time_diff_count_5y, 0) as dam_avg_time_diff
from yearly_dam_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
