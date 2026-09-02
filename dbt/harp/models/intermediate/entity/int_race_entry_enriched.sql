{{config(
  materialized='incremental',
  on_schema_change='sync_all_columns',
  unique_key=['race_id', 'kettonum'],
  tags=['prd'],
  indexes=[
    {'columns': ['held_date']},
    {'columns': ['race_id', 'kettonum']}
  ]
) }}
 

with temp as (
select 
    *
from {{ ref('fct_race_entry') }} re
left join {{ ref('fct_race') }} r
    using (race_id)
),

wood_ranked as (
  select
    te.race_id,
    te.kettonum,
    wc.tozai_cd,
    wc.lap_time_1,
    wc.lap_time_2,
    wc.haron_time_4,
    wc.lap_time_1_z_tozai_day,
    wc.haron_time_4_z_tozai_day,
    wc.haron_time_6,
    wc.haron_time_6_min,
    wc.lap_time_1_diff_avg,
    wc.lap_time_1_diff_min,
    wc.lap_time_1_min,
    wc.accel_flag,
    row_number() over (
      partition by te.race_id, te.kettonum 
      order by wc.lap_time_1 asc, wc.chokyo_date desc
    ) as rn
  from temp te
  left join {{ ref('fct_training_work_wood') }} wc
    on wc.kettonum = te.kettonum
    and wc.chokyo_date < te.held_date - interval '2 days'
    and wc.chokyo_date >= te.held_date - interval '4 days'
),
wood as (
  select
    race_id,
    kettonum,
    tozai_cd,
    lap_time_1,
    lap_time_2,
    haron_time_4,
    lap_time_1_z_tozai_day,
    haron_time_4_z_tozai_day,
    haron_time_6,
    lap_time_1_diff_avg,
    lap_time_1_diff_min,
    lap_time_1_min,
    haron_time_6_min,
    accel_flag
  from wood_ranked
  where rn = 1 or rn is null
),
wood_week1_ranked as (
  select
    te.race_id,
    te.kettonum,
    wc.tozai_cd,
    wc.lap_time_1,
    wc.lap_time_2,
    wc.haron_time_4,
    wc.lap_time_1_z_tozai_day,
    wc.haron_time_4_z_tozai_day,
    wc.haron_time_6,
    wc.haron_time_6_min,
    wc.lap_time_1_diff_avg,
    wc.lap_time_1_diff_min,
    wc.lap_time_1_min,
    wc.accel_flag,
    row_number() over (
      partition by te.race_id, te.kettonum 
      order by wc.lap_time_1 asc, wc.chokyo_date desc
    ) as rn
  from temp te
  left join {{ ref('fct_training_work_wood') }} wc
    on wc.kettonum = te.kettonum
    and wc.chokyo_date < te.held_date - interval '9 days'
    and wc.chokyo_date >= te.held_date - interval '11 days'
),
wood_week1 as (
  select
    race_id,
    kettonum,
    tozai_cd,
    lap_time_1,
    lap_time_2,
    haron_time_4,
    lap_time_1_z_tozai_day,
    haron_time_4_z_tozai_day,
    haron_time_6,
    lap_time_1_diff_avg,
    lap_time_1_diff_min,
    lap_time_1_min,
    haron_time_6_min,
    accel_flag
  from wood_week1_ranked
  where rn = 1 or rn is null
),
hanro_ranked as (
  select
  te.race_id,
    te.kettonum,
  ha.tozai_cd,
  ha.lap_time_1,
  ha.lap_time_2,
  ha.haron_time_4,
  ha.lap_time_1_z_tozai_day,
  ha.haron_time_4_z_tozai_day,
  ha.haron_time_4_diff_avg,
  ha.haron_time_4_diff_min,
  ha.haron_time_4_min,
  ha.lap_time_1_min,
  ha.accel_flag,
  row_number() over (
      partition by te.race_id, te.kettonum 
      order by ha.haron_time_4 asc, ha.chokyo_date desc
    ) as rn
  from temp te
  left join {{ ref('fct_training_work_hanro') }} ha
    on ha.kettonum = te.kettonum
    and ha.chokyo_date < te.held_date - interval '2 days'
    and ha.chokyo_date >= te.held_date - interval '4 days'

),
hanro as (
   select
    race_id,
    kettonum,
    tozai_cd,
    lap_time_1,
    lap_time_2,
    haron_time_4,
    lap_time_1_z_tozai_day,
    haron_time_4_z_tozai_day,
    haron_time_4_diff_avg,
    haron_time_4_diff_min,
    haron_time_4_min,
    lap_time_1_min,
    accel_flag
  from hanro_ranked
  where rn = 1 or rn is null
),
hanro_week1_ranked as (
  select
  te.race_id,
    te.kettonum,
  ha.tozai_cd,
  ha.lap_time_1,
  ha.lap_time_2,
  ha.haron_time_4,
  ha.lap_time_1_z_tozai_day,
  ha.haron_time_4_z_tozai_day,
  ha.haron_time_4_diff_avg,
  ha.haron_time_4_diff_min,
  ha.haron_time_4_min,
  ha.lap_time_1_min,
  ha.accel_flag,
  row_number() over (
      partition by te.race_id, te.kettonum 
      order by ha.haron_time_4 asc, ha.chokyo_date desc
    ) as rn
  from temp te
  left join {{ ref('fct_training_work_hanro') }} ha
    on ha.kettonum = te.kettonum
    and ha.chokyo_date < te.held_date - interval '9 days'
    and ha.chokyo_date >= te.held_date - interval '11 days'

),
hanro_week1 as (
   select
    race_id,
    kettonum,
    tozai_cd,
    lap_time_1,
    lap_time_2,
    haron_time_4,
    lap_time_1_z_tozai_day,
    haron_time_4_z_tozai_day,
    haron_time_4_diff_avg,
    haron_time_4_diff_min,
    haron_time_4_min,
    lap_time_1_min,
    accel_flag
  from hanro_week1_ranked
  where rn = 1 or rn is null
)
select
  re.race_id,
  re.kettonum,
  re.horse_name,
  re.horse_number,
  re.gate_number,
  re.jockey_cd,
  re.jockey_cat,
  re.sire_id,
  re.sire_name,
  re.dam_id,
  re.damsire_id,
  re.sire_cat,
  re.breeder_cd,
  re.trainer_cd,
  re.age,
  re.h_weight,
  re.h_weight_bin,
  re.weight_change,
  re.dm_rank,
  re.sex_cd,
  re.kinryo,
  re.tozai_cd,
  re.popularity,
  re.odds_tansho,
  re.result_order,
  re.blinker_cd,
  re.running_style_cd,
  re.rank_3c,
  re.rank_4c,
  re.agari3f,
  rank() over (
    partition by re.race_id
    order by re.agari3f asc nulls last
  ) as agari3f_rank_in_race,
  case
    when re.agari3f is null then null
    when re.num_starters <= 1 then 0::float
    else (
      rank() over (
        partition by re.race_id
        order by re.agari3f asc nulls last
      ) - 1
    ) / nullif(re.num_starters - 1, 0)::float
  end as agari3f_rank_percentile_in_race,
  re.time_diff,
  re.time_sec,
  re.is_win,
  re.track_cd,
  re.held_date,
  date_trunc('month',re.held_date) as held_year_month,
  re.held_year,
  re.jyo_cd,
  re.distance_m,
  re.surface,
  re.surface_condition,
  re.surface_condition_cd,
  re.tenko_cd,
  re.jyuryo_cd,
  re.course_kubun_cd,
  re.old_cd,
  re.race_level,
  re.num_starters,
  re.ten3f,
  re.ten4f,
  re.agari3f_race,
  re.agari4f_race,
  re.ten3f_ntile,
  re.course_cluster,
  re.turn_direction,
  re.turn_direction_cd,
  re.straight_distance_m,
  re.has_homestretch_slope,
  re.race_pace,
    w.lap_time_1 as wood_lap_time_1,
    w.lap_time_2 as wood_lap_time_2,
    w.haron_time_4 as wood_haron_time_4,
    w.lap_time_1_z_tozai_day as wood_lap_time_1_z_tozai_day,
    w.haron_time_4_z_tozai_day as wood_haron_time_4_z_tozai_day,
    {{ training_joint_bin3_category("w.haron_time_4_z_tozai_day", "w.lap_time_1_z_tozai_day") }} as wood_4f1f_profile_cat3,
    w.tozai_cd as wood_tozai_cd,
    case
      when w.lap_time_1 is not null and w.haron_time_4 is not null
        then (w.haron_time_4 - w.lap_time_1) / 3.0 - w.lap_time_1
      else null
    end as wood_late_sharpness,
    w.haron_time_6 as wood_haron_time_6,
    w.haron_time_6_min as wood_haron_time_6_min,
    w.lap_time_1_min as wood_lap_time_1_min,
    w.accel_flag as wood_accel_flag,
    ww.lap_time_1 as week1_wood_lap_time_1,
    ww.lap_time_2 as week1_wood_lap_time_2,
    ww.haron_time_4 as week1_wood_haron_time_4,
    ww.lap_time_1_z_tozai_day as week1_wood_lap_time_1_z_tozai_day,
    ww.haron_time_4_z_tozai_day as week1_wood_haron_time_4_z_tozai_day,
    ww.tozai_cd as week1_wood_tozai_cd,
    case
      when ww.lap_time_1 is not null and ww.haron_time_4 is not null
        then (ww.haron_time_4 - ww.lap_time_1) / 3.0 - ww.lap_time_1
      else null
    end as week1_wood_late_sharpness,
    ww.haron_time_6 as week1_wood_haron_time_6,
    ww.haron_time_6_min as week1_wood_haron_time_6_min,
    ww.lap_time_1_min as week1_wood_lap_time_1_min,
    ww.accel_flag as week1_wood_accel_flag,
    -- w.lap_time_1_diff_avg as wood_lap_time_1_diff_avg,
    -- w.lap_time_1_diff_min as wood_lap_time_1_diff_min,
    h.lap_time_1 as hanro_lap_time_1,
    h.lap_time_2 as hanro_lap_time_2,
    h.haron_time_4 as hanro_haron_time_4,
    h.lap_time_1_z_tozai_day as hanro_lap_time_1_z_tozai_day,
    h.haron_time_4_z_tozai_day as hanro_haron_time_4_z_tozai_day,
    {{ training_joint_bin3_category("h.haron_time_4_z_tozai_day", "h.lap_time_1_z_tozai_day") }} as hanro_4f1f_profile_cat3,
    h.tozai_cd as hanro_tozai_cd,
    case
      when h.lap_time_1 is not null and h.haron_time_4 is not null
        then (h.haron_time_4 - h.lap_time_1) / 3.0 - h.lap_time_1
      else null
    end as hanro_late_sharpness,
    h.haron_time_4_min as hanro_haron_time_4_min,
    h.lap_time_1_min as hanro_lap_time_1_min,
    h.accel_flag as hanro_accel_flag,
    hw.lap_time_1 as week1_hanro_lap_time_1,
    hw.lap_time_2 as week1_hanro_lap_time_2,
    hw.haron_time_4 as week1_hanro_haron_time_4,
    hw.lap_time_1_z_tozai_day as week1_hanro_lap_time_1_z_tozai_day,
    hw.haron_time_4_z_tozai_day as week1_hanro_haron_time_4_z_tozai_day,
    hw.tozai_cd as week1_hanro_tozai_cd,
    case
      when hw.lap_time_1 is not null and hw.haron_time_4 is not null
        then (hw.haron_time_4 - hw.lap_time_1) / 3.0 - hw.lap_time_1
      else null
    end as week1_hanro_late_sharpness,
    hw.haron_time_4_min as week1_hanro_haron_time_4_min,
    hw.lap_time_1_min as week1_hanro_lap_time_1_min,
    hw.accel_flag as week1_hanro_accel_flag,
    -- h.haron_time_4_diff_avg as hanro_haron_time_4_diff_avg,
    -- h.haron_time_4_diff_min as hanro_haron_time_4_diff_min,
    
    re.race_time_sec as time_sec_race,
    --人気レース内比率（小さいほど人気）
    re.popularity / nullif(re.num_starters, 0)::float as popularity_ratio,

    re.horse_number / nullif(re.num_starters, 0)::float as horse_number_ratio,
    -- 上り相対性能（小さいほど良い：馬の上がりが速い）


    -- ロングスパート指標
    (re.agari4f_race - re.agari3f_race) + re.agari3f as sprint_decay,

    -- 位置取り系（小さいほど前）
    re.rank_3c / nullif(re.num_starters, 0)::float as corner3_pos,
    re.rank_4c / nullif(re.num_starters, 0)::float as corner4_pos,

    -- 開催月
    extract(month from re.held_date) as held_month,
    -- 年齢月
    (re.age) * 12 + extract(month from re.held_date) as age_month,
    case when old_cd in (1,2) then re.held_date  - re.birth_date
          else null
         end as age_days,
    -- レースペース
    re.ten3f - re.agari3f_race as pace_type,

    -- （Synergy用）向きを揃えた“良いほど大きい”指標
    -- 位置取り：前ほど大きい（corner4_posは小さいほど前なので反転）
    (1 - (re.rank_4c / nullif(re.num_starters, 0)::float)) as pos4_good,
    -- 上がり：良いほど大きい（relative_agari3fは小さいほど良いので反転）
    (-(re.agari3f - re.agari3f_race)) as agari_good,

    --遠征フラグ
    case
      when re.tozai_cd = 1 and re.jyo_cd in (3,5,6) then 0
      when re.tozai_cd = 1 and re.jyo_cd not in (8,9,10) then 1
      when re.tozai_cd = 2 and re.jyo_cd in (8,9,10) then 0
      when re.tozai_cd = 2 and re.jyo_cd not in (3,5,6) then 1
      else 2
    end as ensei_type,

    -- 斤量性別補正あり
    case 
      when kinryo is null then null
      when sex_cd = 2 and old_cd = 0 then kinryo+2
      else kinryo
    end as kinryo_adj,

    case 
     when num_starters < 8 and result_order <=2 then 1
     when num_starters >= 8 and result_order <=3 then 1
      else 0
    end as is_place
     
from temp re
left join wood w
    using (race_id, kettonum)
left join wood_week1 ww
    using (race_id, kettonum)
left join hanro h
    using(race_id,kettonum)
left join hanro_week1 hw
    using (race_id, kettonum)
where re.track_cd <50
{% if is_incremental() %}
  and re.held_date >= current_date - interval '7 days'
{% endif %}
