-- 種牡馬別の年次成績（過去{{ var('sire_sample_years') }}年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month'],
  indexes=[{'columns': ['sire_id', 'held_year_month']}],
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
    pos4_agari_synergy,
    time_diff
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_sire as (
  select
    sire_id,
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
    sire_id,
    held_year_month
),

yearly_sire_roll as (
  select
    ys.*,
    sum(ys.starts) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_starts_5y,
    sum(ys.places) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_places_5y,
    sum(ys.wins) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_wins_5y,
    sum(ys.pos4_agari_synergy_sum) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_pos4_agari_synergy_sum_5y,
    sum(ys.pos4_agari_synergy_count) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_pos4_agari_synergy_count_5y,
    sum(ys.time_diff_sum) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_time_diff_sum_5y,
    sum(ys.time_diff_count) over (
      partition by ys.sire_id
      order by ys.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as sire_time_diff_count_5y
  from yearly_sire ys
),

yearly_sire_with_career as (
  select
    ysr.*,
    min(ysr.held_year_month) over (
      partition by ysr.sire_id
    ) as sire_first_held_year_month,
    (
      (
        extract(year from ysr.held_year_month)::int
        - extract(year from min(ysr.held_year_month) over (partition by ysr.sire_id))::int
      ) * 12
      + (
        extract(month from ysr.held_year_month)::int
        - extract(month from min(ysr.held_year_month) over (partition by ysr.sire_id))::int
      )
    )::int as sire_career_months
  from yearly_sire_roll ysr
)

select
  sire_id,
  held_year_month,
  sire_starts_5y,
  sire_places_5y,
  sire_places_5y / nullif(sire_starts_5y, 0) as sire_avg_place_rate,
  ((sire_places_5y + (0.213 * 50))::float
    / nullif(sire_starts_5y + 50, 0)) as sire_avg_place_rate_smooth,
  sire_pos4_agari_synergy_sum_5y::float
    / nullif(sire_pos4_agari_synergy_count_5y, 0) as sire_avg_pos4_agari_synergy,
  sire_time_diff_sum_5y::float
    / nullif(sire_time_diff_count_5y, 0) as sire_avg_time_diff,
  sire_career_months,
  case
    when sire_career_months < 36 then 1
    else 0
  end as sire_is_early_phase_3y
from yearly_sire_with_career
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
