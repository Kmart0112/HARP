{{ config(materialized='table', tags=['prd']) }}



select
  b.race_id,
  b.kettonum,
  b.horse_name,
  b.age,
  b.h_weight,
    case
    when h_weight is null then null
    when h_weight <= 400 then 0
    when h_weight >= 526 then 6
    when h_weight between 401 and 425 then 1
    when h_weight between 426 and 450 then 2
    when h_weight between 451 and 475 then 3
    when h_weight between 476 and 500 then 4
    when h_weight between 501 and 525 then 5
    else null
  end as h_weight_bin,
  b.weight_change,
  b.dm_rank,
  b.sex_cd,
  b.kinryo,
  b.tozai_cd,
  b.horse_number,
  b.gate_number,
  b.jockey_cd,
  b.jockey_cat,
  b.popularity as popularity,
  b.odds_tansho as odds_tansho,
  b.result_order,
  b.blinker_cd,
  b.running_style_cd,
  b.rank_1c,
  b.rank_2c,
  b.rank_3c,
  b.rank_4c,
  b.agari3f,
  b.agari4f,
  log(b.time_diff+1) as time_diff,
  b.time_sec,
  u.sire_cat,
  b.trainer_cd,
  u.breeder_cat,
  u.breeder_cd,
  u.trainer_cat,
  u.sire_id,
  u.sire_name,
  u.dam_id,
  u.damsire_id,
  u.birth_date,
  case when b.result_order = 1 then 1 else 0
  end as is_win
from {{ ref('stg_n_uma_race') }} b
left join {{ ref('stg_n_uma') }} u
  on b.kettonum = u.kettonum_int
