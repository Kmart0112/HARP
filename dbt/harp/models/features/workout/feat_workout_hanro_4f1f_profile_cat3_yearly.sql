{{ config(
  materialized='incremental',
  unique_key=['held_year_month', 'hanro_4f1f_profile_cat3'],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    held_year_month,
    hanro_4f1f_profile_cat3,
    is_place
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and hanro_4f1f_profile_cat3 is not null
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

yearly_profile as (
  select
    held_year_month,
    hanro_4f1f_profile_cat3,
    count(*) as starts,
    sum(is_place) as places
  from base
  group by
    held_year_month,
    hanro_4f1f_profile_cat3
),

yearly_profile_roll as (
  select
    yp.*,
    sum(yp.starts) over (
      partition by yp.hanro_4f1f_profile_cat3
      order by yp.held_year_month
      rows between 35 preceding and 1 preceding
    ) as hanro_4f1f_profile_cat3_starts_3y,
    sum(yp.places) over (
      partition by yp.hanro_4f1f_profile_cat3
      order by yp.held_year_month
      rows between 35 preceding and 1 preceding
    ) as hanro_4f1f_profile_cat3_places_3y
  from yearly_profile yp
)

select
  held_year_month,
  hanro_4f1f_profile_cat3,
  hanro_4f1f_profile_cat3_starts_3y,
  hanro_4f1f_profile_cat3_places_3y,
  case
    when hanro_4f1f_profile_cat3_starts_3y is null or hanro_4f1f_profile_cat3_starts_3y = 0 then null
    else hanro_4f1f_profile_cat3_places_3y::float / nullif(hanro_4f1f_profile_cat3_starts_3y, 0)
  end as hanro_4f1f_profile_place_rate_3y,
  case
    when hanro_4f1f_profile_cat3_starts_3y is null or hanro_4f1f_profile_cat3_starts_3y = 0 then null
    else ((hanro_4f1f_profile_cat3_places_3y + (0.213 * 20))::float / nullif(hanro_4f1f_profile_cat3_starts_3y + 20, 0))
  end as hanro_4f1f_profile_place_rate_3y_smooth
from yearly_profile_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
