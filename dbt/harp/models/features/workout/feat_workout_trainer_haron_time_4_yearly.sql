{{ config(
  materialized='incremental',
  unique_key=['trainer_cd', 'held_year_month'],
  tags=['feature','monthly']
) }}

with incremental_bounds as (
  {{ monthly_incremental_bounds(this, history_years=3) }}
),

base as (
  select
    trainer_cd,
    held_year_month,
    wood_haron_time_4,
    hanro_haron_time_4,
    week1_wood_haron_time_4,
    week1_hanro_haron_time_4
  from {{ ref('feat_race_entry_base') }}
  where held_year_month is not null
    and trainer_cd is not null
    and (
      wood_haron_time_4 is not null
      or hanro_haron_time_4 is not null
      or week1_wood_haron_time_4 is not null
      or week1_hanro_haron_time_4 is not null
    )
  {% if is_incremental() %}
    and held_year_month >= (select hist_from_period from incremental_bounds)
  {% endif %}
),

trainer_monthly as (
  select
    trainer_cd,
    held_year_month,
    count(wood_haron_time_4) as wood_haron_time_4_starts,
    sum(wood_haron_time_4) as wood_haron_time_4_sum,
    sum(power(wood_haron_time_4, 2)) as wood_haron_time_4_sumsq,
    count(hanro_haron_time_4) as hanro_haron_time_4_starts,
    sum(hanro_haron_time_4) as hanro_haron_time_4_sum,
    sum(power(hanro_haron_time_4, 2)) as hanro_haron_time_4_sumsq,
    count(week1_wood_haron_time_4) as week1_wood_haron_time_4_starts,
    sum(week1_wood_haron_time_4) as week1_wood_haron_time_4_sum,
    sum(power(week1_wood_haron_time_4, 2)) as week1_wood_haron_time_4_sumsq,
    count(week1_hanro_haron_time_4) as week1_hanro_haron_time_4_starts,
    sum(week1_hanro_haron_time_4) as week1_hanro_haron_time_4_sum,
    sum(power(week1_hanro_haron_time_4, 2)) as week1_hanro_haron_time_4_sumsq
  from base
  group by
    trainer_cd,
    held_year_month
),

trainer_monthly_roll as (
  select
    tm.*,
    sum(tm.wood_haron_time_4_starts) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_wood_haron_time_4_starts_3y,
    sum(tm.wood_haron_time_4_sum) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_wood_haron_time_4_sum_3y,
    sum(tm.wood_haron_time_4_sumsq) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_wood_haron_time_4_sumsq_3y,
    sum(tm.hanro_haron_time_4_starts) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_hanro_haron_time_4_starts_3y,
    sum(tm.hanro_haron_time_4_sum) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_hanro_haron_time_4_sum_3y,
    sum(tm.hanro_haron_time_4_sumsq) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_hanro_haron_time_4_sumsq_3y,
    sum(tm.week1_wood_haron_time_4_starts) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_wood_haron_time_4_starts_3y,
    sum(tm.week1_wood_haron_time_4_sum) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_wood_haron_time_4_sum_3y,
    sum(tm.week1_wood_haron_time_4_sumsq) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_wood_haron_time_4_sumsq_3y,
    sum(tm.week1_hanro_haron_time_4_starts) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_hanro_haron_time_4_starts_3y,
    sum(tm.week1_hanro_haron_time_4_sum) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_hanro_haron_time_4_sum_3y,
    sum(tm.week1_hanro_haron_time_4_sumsq) over (
      partition by tm.trainer_cd
      order by tm.held_year_month
      rows between 35 preceding and 1 preceding
    ) as trainer_week1_hanro_haron_time_4_sumsq_3y
  from trainer_monthly tm
)

select
  trainer_cd,
  held_year_month,
  trainer_wood_haron_time_4_starts_3y,
  case
    when trainer_wood_haron_time_4_starts_3y is null or trainer_wood_haron_time_4_starts_3y = 0 then null
    else trainer_wood_haron_time_4_sum_3y::float / nullif(trainer_wood_haron_time_4_starts_3y, 0)
  end as trainer_wood_haron_time_4_mean_3y,
  case
    when trainer_wood_haron_time_4_starts_3y is null or trainer_wood_haron_time_4_starts_3y <= 1 then null
    else sqrt(
      greatest(
        (
          trainer_wood_haron_time_4_sumsq_3y
          - power(trainer_wood_haron_time_4_sum_3y, 2) / nullif(trainer_wood_haron_time_4_starts_3y, 0)
        ) / nullif(trainer_wood_haron_time_4_starts_3y - 1, 0),
        0
      )
    )
  end as trainer_wood_haron_time_4_std_3y,
  trainer_hanro_haron_time_4_starts_3y,
  case
    when trainer_hanro_haron_time_4_starts_3y is null or trainer_hanro_haron_time_4_starts_3y = 0 then null
    else trainer_hanro_haron_time_4_sum_3y::float / nullif(trainer_hanro_haron_time_4_starts_3y, 0)
  end as trainer_hanro_haron_time_4_mean_3y,
  case
    when trainer_hanro_haron_time_4_starts_3y is null or trainer_hanro_haron_time_4_starts_3y <= 1 then null
    else sqrt(
      greatest(
        (
          trainer_hanro_haron_time_4_sumsq_3y
          - power(trainer_hanro_haron_time_4_sum_3y, 2) / nullif(trainer_hanro_haron_time_4_starts_3y, 0)
        ) / nullif(trainer_hanro_haron_time_4_starts_3y - 1, 0),
        0
      )
    )
  end as trainer_hanro_haron_time_4_std_3y,
  trainer_week1_wood_haron_time_4_starts_3y,
  case
    when trainer_week1_wood_haron_time_4_starts_3y is null or trainer_week1_wood_haron_time_4_starts_3y = 0 then null
    else trainer_week1_wood_haron_time_4_sum_3y::float / nullif(trainer_week1_wood_haron_time_4_starts_3y, 0)
  end as trainer_week1_wood_haron_time_4_mean_3y,
  case
    when trainer_week1_wood_haron_time_4_starts_3y is null or trainer_week1_wood_haron_time_4_starts_3y <= 1 then null
    else sqrt(
      greatest(
        (
          trainer_week1_wood_haron_time_4_sumsq_3y
          - power(trainer_week1_wood_haron_time_4_sum_3y, 2) / nullif(trainer_week1_wood_haron_time_4_starts_3y, 0)
        ) / nullif(trainer_week1_wood_haron_time_4_starts_3y - 1, 0),
        0
      )
    )
  end as trainer_week1_wood_haron_time_4_std_3y,
  trainer_week1_hanro_haron_time_4_starts_3y,
  case
    when trainer_week1_hanro_haron_time_4_starts_3y is null or trainer_week1_hanro_haron_time_4_starts_3y = 0 then null
    else trainer_week1_hanro_haron_time_4_sum_3y::float / nullif(trainer_week1_hanro_haron_time_4_starts_3y, 0)
  end as trainer_week1_hanro_haron_time_4_mean_3y,
  case
    when trainer_week1_hanro_haron_time_4_starts_3y is null or trainer_week1_hanro_haron_time_4_starts_3y <= 1 then null
    else sqrt(
      greatest(
        (
          trainer_week1_hanro_haron_time_4_sumsq_3y
          - power(trainer_week1_hanro_haron_time_4_sum_3y, 2) / nullif(trainer_week1_hanro_haron_time_4_starts_3y, 0)
        ) / nullif(trainer_week1_hanro_haron_time_4_starts_3y - 1, 0),
        0
      )
    )
  end as trainer_week1_hanro_haron_time_4_std_3y
from trainer_monthly_roll
{% if is_incremental() %}
where held_year_month >= (select recalc_from_period from incremental_bounds)
{% endif %}
