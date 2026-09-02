-- 種牡馬×年齢別の年次成績（過去{{ var('sire_sample_years') }}年移動平均）
{{ config(
  materialized='incremental',
  unique_key=['sire_id', 'held_year_month', 'age'],
  indexes=[{'columns': ['sire_id', 'held_year_month', 'age']}],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=var('sire_sample_years')) }}
),

base as (
  select
    sire_id,
    held_year_month,
    case
      when age >= 8 then 8
      else age
    end as age,
    is_place,
    pos4_agari_synergy
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and sire_id is not null
    and age is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

age_yearly as (
  select
    *
  from {{ ref('feat_age_yearly') }}
),

yearly_sire_age as (
  select
    sire_id,
    held_year_month,
    age,
    count(*) as starts,
    sum(is_place) as places,
    sum(pos4_agari_synergy) as pos4_agari_synergy_sum,
    count(pos4_agari_synergy) as pos4_agari_synergy_count
  from base
  group by
    sire_id,
    held_year_month,
    age
),

yearly_sire_age_with_prior as (
  select
    ysa.*,
    ay.age_place_rate_3y as age_place_rate_3y_prior
  from yearly_sire_age ysa
  left join age_yearly ay
    on ysa.age = ay.age
    and extract(year from ysa.held_year_month)::int = ay.held_year
),

yearly_sire_age_roll as (
  select
    ysap.*,
    sum(ysap.starts) over (
      partition by ysap.sire_id, ysap.age
      order by ysap.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_age_sire_starts_5y,
    sum(ysap.places) over (
      partition by ysap.sire_id, ysap.age
      order by ysap.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_age_sire_places_5y,
    sum(ysap.pos4_agari_synergy_sum) over (
      partition by ysap.sire_id, ysap.age
      order by ysap.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_age_sire_pos4_agari_synergy_sum_5y,
    sum(ysap.pos4_agari_synergy_count) over (
      partition by ysap.sire_id, ysap.age
      order by ysap.held_year_month
      rows between ({{ var('sire_sample_years') }} * 12 - 1) preceding and 1 preceding
    ) as same_age_sire_pos4_agari_synergy_count_5y
  from yearly_sire_age_with_prior ysap
)

select
  sire_id,
  held_year_month,
  age,
  same_age_sire_starts_5y,
  same_age_sire_places_5y,
  age_place_rate_3y_prior,
  same_age_sire_pos4_agari_synergy_sum_5y::float
    / nullif(same_age_sire_pos4_agari_synergy_count_5y, 0)
    as same_age_sire_avg_pos4_agari_synergy,
  (
    (
      coalesce(same_age_sire_places_5y, 0)
      + (coalesce(age_place_rate_3y_prior, 0.213) * 20)
    )::float
    / nullif(coalesce(same_age_sire_starts_5y, 0) + 20, 0)
  ) as same_age_sire_avg_place_rate_smooth_prev_age
from yearly_sire_age_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
