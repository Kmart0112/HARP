{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['race_week_static']
) }}

with entries as (
  select *
  from {{ ref('stg_n_uma_race_all') }}
  where held_date >= '2008-01-01'
  {% if is_incremental() %}
    and held_date between
      '{{ var("race_from_date", "1900-01-01") }}'::date
      and '{{ var("race_to_date", "2999-12-31") }}'::date
  {% endif %}
),

horses as (
  select
    kettonum_int,
    sire_cat,
    breeder_cat,
    breeder_cd,
    trainer_cat,
    sire_id,
    sire_name,
    dam_id,
    damsire_id,
    birth_date
  from {{ ref('stg_n_uma') }}
)

select
  e.race_id,
  e.kettonum,
  e.held_date,
  e.datakubun,
  e.horse_name,
  e.age,
  e.h_weight,
  case
    when e.h_weight is null then null
    when e.h_weight <= 400 then 0
    when e.h_weight >= 526 then 6
    when e.h_weight between 401 and 425 then 1
    when e.h_weight between 426 and 450 then 2
    when e.h_weight between 451 and 475 then 3
    when e.h_weight between 476 and 500 then 4
    when e.h_weight between 501 and 525 then 5
    else null
  end as h_weight_bin,
  e.weight_change,
  e.sex_cd,
  e.kinryo,
  e.tozai_cd,
  e.horse_number,
  e.gate_number,
  e.popularity,
  e.odds_tansho,
  e.jockey_cd,
  e.jockey_cat,
  e.trainer_cd,
  e.blinker_cd,
  e.ijyo_cd,
  e.ijyo_cd is not null as is_scratched_or_excluded,
  e.has_result,
  h.sire_cat,
  h.breeder_cat,
  h.breeder_cd,
  h.trainer_cat,
  h.sire_id,
  h.sire_name,
  h.dam_id,
  h.damsire_id,
  h.birth_date
from entries e
left join horses h
  on e.kettonum = h.kettonum_int
