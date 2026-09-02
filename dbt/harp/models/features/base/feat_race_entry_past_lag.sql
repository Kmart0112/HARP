{{ config(materialized='incremental', tags=['feature','main'], unique_key=['race_id', 'kettonum']) }}

with past_lag as (
  select
    *
  from {{ ref('int_race_entry_past_lag_base') }}
)

-- 過去走の集計（平均など）
select
    w.race_id,
    w.kettonum,
    w.held_date,
    w.is_shokyu,
    w.race_level_diff,
    w.is_jockey_change,
    w.is_surface_changed,
    w.horse_corner4_sd3,
    w.p1_kinryo,
    w.p1_distance_m,
    w.p1_weight,
    w.p1_weight_change,
    w.same_cluster_avg_pos4_agari_synergy,
    w.p1_weight::float / nullif(w.h_weight,0) ::float as weight_change_ratio,
    (distance_m -p1_distance_m)::float / nullif(distance_m, 0) as distance_change,
    (course_cluster != p1_course_cluster)::int as course_cluster_change,
    p1_wood_lap_time_1,
    p1_wood_lap_time_1_z_tozai_day,
    p1_trainer_wood_lap_time_1_fast_excess_z_3y,
    p1_hanro_lap_time_1,
    p1_hanro_lap_time_1_z_tozai_day,
    p1_trainer_hanro_lap_time_1_fast_excess_z_3y,

      p1_pos4_agari_synergy,
      p2_pos4_agari_synergy,
      p3_pos4_agari_synergy,
      p1_time_diff,
      p2_time_diff,
      p3_time_diff,
      p1_ten3f_vs_avg,
      p2_ten3f_vs_avg,
      p3_ten3f_vs_avg,
      p1_pace_front_disadvantage,
      p2_pace_front_disadvantage,
      p3_pace_front_disadvantage,
      p1_time_vs_pace_avg,
      p2_time_vs_pace_avg,
      p3_time_vs_pace_avg,
      p1_jyo_cd,
      p2_jyo_cd,
      p3_jyo_cd,
      p1_race_level,
      blinker_added,

    -- 有効レース数
    nullif((case when p1_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p2_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p3_pos4_agari_synergy is null then 0 else 1 end),0) as num_past3_races,
    nullif((case when p1_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p2_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p3_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p4_pos4_agari_synergy is null then 0 else 1 end) +
          (case when p5_pos4_agari_synergy is null then 0 else 1 end),0) as num_past5_races,

   ( (case when abs(distance_m -p1_distance_m) >= 400 then 1 else 0 end) +
    (case when abs(distance_m -p2_distance_m) >= 400 then 1 else 0 end) +
    (case when abs(distance_m -p3_distance_m) >= 400 then 1 else 0 end) +
    (case when surface != p1_surface then 1 else 0 end) +
    (case when surface != p2_surface then 1 else 0 end) +
    (case when surface != p3_surface then 1 else 0 end))
    as condition_change_score,

    ( (case when abs(distance_m -p1_distance_m) >= 400 then 1 else 0 end) +
    (case when abs(distance_m -p2_distance_m) >= 400 then 1 else 0 end) +
    (case when abs(distance_m -p3_distance_m) >= 400 then 1 else 0 end))  as distance_change_score,

    ((case when surface != p1_surface then 1 else 0 end) +
    (case when surface != p2_surface then 1 else 0 end) +
    (case when surface != p3_surface then 1 else 0 end)) as surface_change_score,  

    ((case when course_cluster != p1_course_cluster then 1 else 0 end) +
    (case when course_cluster != p2_course_cluster then 1 else 0 end) +
    (case when course_cluster != p3_course_cluster then 1 else 0 end)) as course_cluster_change_score,
    p1_course_cluster,


    (coalesce(p1_kinryo, 0) + coalesce(p2_kinryo, 0) + coalesce(p3_kinryo, 0))
      / nullif(
          (case when p1_kinryo is null then 0 else 1 end)
        + (case when p2_kinryo is null then 0 else 1 end)
        + (case when p3_kinryo is null then 0 else 1 end),
        0
      ) as horse_kinryo_avg3,

    -- 直近3走 平均（NULL除外）
    (coalesce(p1_rel_agari3f, 0) + coalesce(p2_rel_agari3f, 0) + coalesce(p3_rel_agari3f, 0))
      / nullif(
          (case when p1_rel_agari3f is null then 0 else 1 end)
        + (case when p2_rel_agari3f is null then 0 else 1 end)
        + (case when p3_rel_agari3f is null then 0 else 1 end),
        0
      ) as horse_rel_agari3f_avg3,
    floor(
      (
      coalesce(p1_agari3f_rank, 0)
      + coalesce(p2_agari3f_rank, 0)
      + coalesce(p3_agari3f_rank, 0)
    )::float
      / nullif(
          (case when p1_agari3f_rank is null then 0 else 1 end)
        + (case when p2_agari3f_rank is null then 0 else 1 end)
        + (case when p3_agari3f_rank is null then 0 else 1 end),
        0
      )
    )::int as agari3f_rank_avg3,
    (
      coalesce(p1_agari3f_rank_percentile, 0)
      + coalesce(p2_agari3f_rank_percentile, 0)
      + coalesce(p3_agari3f_rank_percentile, 0)
    )::float
      / nullif(
          (case when p1_agari3f_rank_percentile is null then 0 else 1 end)
        + (case when p2_agari3f_rank_percentile is null then 0 else 1 end)
        + (case when p3_agari3f_rank_percentile is null then 0 else 1 end),
        0
      ) as agari3f_rank_percentile_avg3,
    (coalesce(p1_rel_agari3f, 0) + coalesce(p2_rel_agari3f, 0) + coalesce(p3_rel_agari3f, 0) + coalesce(p4_rel_agari3f, 0) + coalesce(p5_rel_agari3f, 0))
      / nullif(
          (case when p1_rel_agari3f is null then 0 else 1 end)
        + (case when p2_rel_agari3f is null then 0 else 1 end)
        + (case when p3_rel_agari3f is null then 0 else 1 end)
        + (case when p4_rel_agari3f is null then 0 else 1 end)
        + (case when p5_rel_agari3f is null then 0 else 1 end),
        0
      ) as horse_rel_agari3f_avg5,
    ((case when p1_rel_agari3f is null then 0 else p1_rel_agari3f * 0.40 end)
      + (case when p2_rel_agari3f is null then 0 else p2_rel_agari3f * 0.25 end)
      + (case when p3_rel_agari3f is null then 0 else p3_rel_agari3f * 0.16 end)
      + (case when p4_rel_agari3f is null then 0 else p4_rel_agari3f * 0.11 end)
      + (case when p5_rel_agari3f is null then 0 else p5_rel_agari3f * 0.08 end))
      / nullif(
          (case when p1_rel_agari3f is null then 0 else 0.40 end)
        + (case when p2_rel_agari3f is null then 0 else 0.25 end)
        + (case when p3_rel_agari3f is null then 0 else 0.16 end)
        + (case when p4_rel_agari3f is null then 0 else 0.11 end)
        + (case when p5_rel_agari3f is null then 0 else 0.08 end),
        0
      ) as horse_rel_agari3f_wavg5_recent,

    (coalesce(p1_corner4, 0) + coalesce(p2_corner4, 0) + coalesce(p3_corner4, 0))
      / nullif(
          (case when p1_corner4 is null then 0 else 1 end)
        + (case when p2_corner4 is null then 0 else 1 end)
        + (case when p3_corner4 is null then 0 else 1 end),
        0
      ) as horse_corner4_avg3,
    (coalesce(p1_corner4, 0) + coalesce(p2_corner4, 0) + coalesce(p3_corner4, 0) + coalesce(p4_corner4, 0) + coalesce(p5_corner4, 0))
      / nullif(
          (case when p1_corner4 is null then 0 else 1 end)
        + (case when p2_corner4 is null then 0 else 1 end)
        + (case when p3_corner4 is null then 0 else 1 end)
        + (case when p4_corner4 is null then 0 else 1 end)
        + (case when p5_corner4 is null then 0 else 1 end),
        0
      ) as horse_corner4_avg5,
    ((case when p1_corner4 is null then 0 else p1_corner4 * 0.40 end)
      + (case when p2_corner4 is null then 0 else p2_corner4 * 0.25 end)
      + (case when p3_corner4 is null then 0 else p3_corner4 * 0.16 end)
      + (case when p4_corner4 is null then 0 else p4_corner4 * 0.11 end)
      + (case when p5_corner4 is null then 0 else p5_corner4 * 0.08 end))
      / nullif(
          (case when p1_corner4 is null then 0 else 0.40 end)
        + (case when p2_corner4 is null then 0 else 0.25 end)
        + (case when p3_corner4 is null then 0 else 0.16 end)
        + (case when p4_corner4 is null then 0 else 0.11 end)
        + (case when p5_corner4 is null then 0 else 0.08 end),
        0
      ) as horse_corner4_wavg5_recent,
    {{ lag_stddev_sample(['p1_corner4', 'p2_corner4', 'p3_corner4', 'p4_corner4', 'p5_corner4']) }} as horse_corner4_sd5,
    {{ lag_trend('p1_corner4', 'p5_corner4', 4) }} as horse_corner4_trend5,
      p1_corner4,
      p2_corner4,
      p3_corner4,

    (coalesce(p1_time_vs_avg, 0) + coalesce(p2_time_vs_avg, 0) + coalesce(p3_time_vs_avg, 0))
      / nullif(
          (case when p1_time_vs_avg is null then 0 else 1 end)
        + (case when p2_time_vs_avg is null then 0 else 1 end)
        + (case when p3_time_vs_avg is null then 0 else 1 end),
        0
      ) as time_vs_avg_avg3,
    (coalesce(p1_time_vs_avg, 0) + coalesce(p2_time_vs_avg, 0) + coalesce(p3_time_vs_avg, 0) + coalesce(p4_time_vs_avg, 0) + coalesce(p5_time_vs_avg, 0))
      / nullif(
          (case when p1_time_vs_avg is null then 0 else 1 end)
        + (case when p2_time_vs_avg is null then 0 else 1 end)
        + (case when p3_time_vs_avg is null then 0 else 1 end)
        + (case when p4_time_vs_avg is null then 0 else 1 end)
        + (case when p5_time_vs_avg is null then 0 else 1 end),
        0
      ) as time_vs_avg_avg5,
    ((case when p1_time_vs_avg is null then 0 else p1_time_vs_avg * 0.40 end)
      + (case when p2_time_vs_avg is null then 0 else p2_time_vs_avg * 0.25 end)
      + (case when p3_time_vs_avg is null then 0 else p3_time_vs_avg * 0.16 end)
      + (case when p4_time_vs_avg is null then 0 else p4_time_vs_avg * 0.11 end)
      + (case when p5_time_vs_avg is null then 0 else p5_time_vs_avg * 0.08 end))
      / nullif(
          (case when p1_time_vs_avg is null then 0 else 0.40 end)
        + (case when p2_time_vs_avg is null then 0 else 0.25 end)
        + (case when p3_time_vs_avg is null then 0 else 0.16 end)
        + (case when p4_time_vs_avg is null then 0 else 0.11 end)
        + (case when p5_time_vs_avg is null then 0 else 0.08 end),
        0
      ) as time_vs_avg_wavg5_recent,
    {{ lag_stddev_sample(['p1_time_vs_avg', 'p2_time_vs_avg', 'p3_time_vs_avg', 'p4_time_vs_avg', 'p5_time_vs_avg']) }} as time_vs_avg_sd5,
    {{ lag_trend('p1_time_vs_avg', 'p5_time_vs_avg', 4) }} as time_vs_avg_trend5,

    (coalesce(p1_ten3f_vs_avg, 0) + coalesce(p2_ten3f_vs_avg, 0) + coalesce(p3_ten3f_vs_avg, 0))
      / nullif(
          (case when p1_ten3f_vs_avg is null then 0 else 1 end)
        + (case when p2_ten3f_vs_avg is null then 0 else 1 end)
        + (case when p3_ten3f_vs_avg is null then 0 else 1 end),
        0
      ) as ten3f_vs_avg_avg3,

    (coalesce(p1_pace_front_disadvantage, 0) + coalesce(p2_pace_front_disadvantage, 0) + coalesce(p3_pace_front_disadvantage, 0))
      / nullif(
          (case when p1_pace_front_disadvantage is null then 0 else 1 end)
        + (case when p2_pace_front_disadvantage is null then 0 else 1 end)
        + (case when p3_pace_front_disadvantage is null then 0 else 1 end),
        0
      ) as pace_front_disadvantage_avg3,

      (coalesce(p1_time_vs_pace_avg, 0) + coalesce(p2_time_vs_pace_avg, 0) + coalesce(p3_time_vs_pace_avg, 0))
      / nullif(
          (case when p1_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p2_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p3_time_vs_pace_avg is null then 0 else 1 end),
        0
      ) as time_vs_pace_avg_avg3,
    (coalesce(p1_time_vs_pace_avg, 0) + coalesce(p2_time_vs_pace_avg, 0) + coalesce(p3_time_vs_pace_avg, 0) + coalesce(p4_time_vs_pace_avg, 0) + coalesce(p5_time_vs_pace_avg, 0))
      / nullif(
          (case when p1_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p2_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p3_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p4_time_vs_pace_avg is null then 0 else 1 end)
        + (case when p5_time_vs_pace_avg is null then 0 else 1 end),
        0
      ) as time_vs_pace_avg_avg5,
    ((case when p1_time_vs_pace_avg is null then 0 else p1_time_vs_pace_avg * 0.40 end)
      + (case when p2_time_vs_pace_avg is null then 0 else p2_time_vs_pace_avg * 0.25 end)
      + (case when p3_time_vs_pace_avg is null then 0 else p3_time_vs_pace_avg * 0.16 end)
      + (case when p4_time_vs_pace_avg is null then 0 else p4_time_vs_pace_avg * 0.11 end)
      + (case when p5_time_vs_pace_avg is null then 0 else p5_time_vs_pace_avg * 0.08 end))
      / nullif(
          (case when p1_time_vs_pace_avg is null then 0 else 0.40 end)
        + (case when p2_time_vs_pace_avg is null then 0 else 0.25 end)
        + (case when p3_time_vs_pace_avg is null then 0 else 0.16 end)
        + (case when p4_time_vs_pace_avg is null then 0 else 0.11 end)
        + (case when p5_time_vs_pace_avg is null then 0 else 0.08 end),
        0
      ) as time_vs_pace_avg_wavg5_recent,

      ((case when p1_time_vs_avg_adjusted is null then 0 else p1_time_vs_avg_adjusted * 0.5 end) 
      + (case when p2_time_vs_avg_adjusted is null then 0 else p2_time_vs_avg_adjusted * 0.3 end) + 
      (case when p3_time_vs_avg_adjusted is null then 0 else p3_time_vs_avg_adjusted * 0.2 end))
      / nullif(
          (case when p1_time_vs_avg_adjusted is null then 0 else 0.5 end)
        + (case when p2_time_vs_avg_adjusted is null then 0 else 0.3 end)
        + (case when p3_time_vs_avg_adjusted is null then 0 else 0.2 end),
        0
      ) as time_vs_avg_adjusted_avg3,
    (coalesce(p1_time_vs_avg_adjusted, 0) + coalesce(p2_time_vs_avg_adjusted, 0) + coalesce(p3_time_vs_avg_adjusted, 0) + coalesce(p4_time_vs_avg_adjusted, 0) + coalesce(p5_time_vs_avg_adjusted, 0))
      / nullif(
          (case when p1_time_vs_avg_adjusted is null then 0 else 1 end)
        + (case when p2_time_vs_avg_adjusted is null then 0 else 1 end)
        + (case when p3_time_vs_avg_adjusted is null then 0 else 1 end)
        + (case when p4_time_vs_avg_adjusted is null then 0 else 1 end)
        + (case when p5_time_vs_avg_adjusted is null then 0 else 1 end),
        0
      ) as time_vs_avg_adjusted_avg5,
    ((case when p1_time_vs_avg_adjusted is null then 0 else p1_time_vs_avg_adjusted * 0.40 end)
      + (case when p2_time_vs_avg_adjusted is null then 0 else p2_time_vs_avg_adjusted * 0.25 end)
      + (case when p3_time_vs_avg_adjusted is null then 0 else p3_time_vs_avg_adjusted * 0.16 end)
      + (case when p4_time_vs_avg_adjusted is null then 0 else p4_time_vs_avg_adjusted * 0.11 end)
      + (case when p5_time_vs_avg_adjusted is null then 0 else p5_time_vs_avg_adjusted * 0.08 end))
      / nullif(
          (case when p1_time_vs_avg_adjusted is null then 0 else 0.40 end)
        + (case when p2_time_vs_avg_adjusted is null then 0 else 0.25 end)
        + (case when p3_time_vs_avg_adjusted is null then 0 else 0.16 end)
        + (case when p4_time_vs_avg_adjusted is null then 0 else 0.11 end)
        + (case when p5_time_vs_avg_adjusted is null then 0 else 0.08 end),
        0
      ) as time_vs_avg_adjusted_wavg5_recent,


      ((case when p1_time_diff is null then 0 else p1_time_diff*0.5 end) 
      + (case when p2_time_diff is null then 0 else p2_time_diff*0.3 end)
       + (case when p3_time_diff is null then 0 else p3_time_diff*0.2 end))
      / nullif(
          (case when p1_time_diff is null then 0 else 0.5 end)
        + (case when p2_time_diff is null then 0 else 0.3 end)
        + (case when p3_time_diff is null then 0 else 0.2 end),
        0
      )  as time_diff_avg3,
    (coalesce(p1_time_diff, 0) + coalesce(p2_time_diff, 0) + coalesce(p3_time_diff, 0) + coalesce(p4_time_diff, 0) + coalesce(p5_time_diff, 0))
      / nullif(
          (case when p1_time_diff is null then 0 else 1 end)
        + (case when p2_time_diff is null then 0 else 1 end)
        + (case when p3_time_diff is null then 0 else 1 end)
        + (case when p4_time_diff is null then 0 else 1 end)
        + (case when p5_time_diff is null then 0 else 1 end),
        0
      ) as time_diff_avg5,
    ((case when p1_time_diff is null then 0 else p1_time_diff * 0.40 end)
      + (case when p2_time_diff is null then 0 else p2_time_diff * 0.25 end)
      + (case when p3_time_diff is null then 0 else p3_time_diff * 0.16 end)
      + (case when p4_time_diff is null then 0 else p4_time_diff * 0.11 end)
      + (case when p5_time_diff is null then 0 else p5_time_diff * 0.08 end))
      / nullif(
          (case when p1_time_diff is null then 0 else 0.40 end)
        + (case when p2_time_diff is null then 0 else 0.25 end)
        + (case when p3_time_diff is null then 0 else 0.16 end)
        + (case when p4_time_diff is null then 0 else 0.11 end)
        + (case when p5_time_diff is null then 0 else 0.08 end),
        0
      ) as time_diff_wavg5_recent,
    {{ lag_stddev_sample(['p1_time_diff', 'p2_time_diff', 'p3_time_diff', 'p4_time_diff', 'p5_time_diff']) }} as time_diff_sd5,
    {{ lag_trend('p1_time_diff', 'p5_time_diff', 4) }} as time_diff_trend5,

    
      ((case when p1_pos4_agari_synergy is null then 0 else p1_pos4_agari_synergy * 0.5 end) + 
      (case when p2_pos4_agari_synergy is null then 0 else p2_pos4_agari_synergy * 0.3 end) + 
      (case when p3_pos4_agari_synergy is null then 0 else p3_pos4_agari_synergy * 0.2 end))
      / nullif(
          (case when p1_pos4_agari_synergy is null then 0 else 0.5 end)
        + (case when p2_pos4_agari_synergy is null then 0 else 0.3 end)
        + (case when p3_pos4_agari_synergy is null then 0 else 0.2 end),
        0
      ) as pos4_agari_synergy_avg3,
    (coalesce(p1_pos4_agari_synergy, 0) + coalesce(p2_pos4_agari_synergy, 0) + coalesce(p3_pos4_agari_synergy, 0) + coalesce(p4_pos4_agari_synergy, 0) + coalesce(p5_pos4_agari_synergy, 0))
      / nullif(
          (case when p1_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p2_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p3_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p4_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p5_pos4_agari_synergy is null then 0 else 1 end),
        0
      ) as pos4_agari_synergy_avg5,
    ((case when p1_pos4_agari_synergy is null then 0 else p1_pos4_agari_synergy * 0.40 end)
      + (case when p2_pos4_agari_synergy is null then 0 else p2_pos4_agari_synergy * 0.25 end)
      + (case when p3_pos4_agari_synergy is null then 0 else p3_pos4_agari_synergy * 0.16 end)
      + (case when p4_pos4_agari_synergy is null then 0 else p4_pos4_agari_synergy * 0.11 end)
      + (case when p5_pos4_agari_synergy is null then 0 else p5_pos4_agari_synergy * 0.08 end))
      / nullif(
          (case when p1_pos4_agari_synergy is null then 0 else 0.40 end)
        + (case when p2_pos4_agari_synergy is null then 0 else 0.25 end)
        + (case when p3_pos4_agari_synergy is null then 0 else 0.16 end)
        + (case when p4_pos4_agari_synergy is null then 0 else 0.11 end)
        + (case when p5_pos4_agari_synergy is null then 0 else 0.08 end),
        0
      ) as pos4_agari_synergy_wavg5_recent,
    {{ lag_stddev_sample(['p1_pos4_agari_synergy', 'p2_pos4_agari_synergy', 'p3_pos4_agari_synergy', 'p4_pos4_agari_synergy', 'p5_pos4_agari_synergy']) }} as pos4_agari_synergy_sd5,
    case
      when p1_pos4_agari_synergy is null or p5_pos4_agari_synergy is null then null
      else (p1_pos4_agari_synergy - p5_pos4_agari_synergy)::float / 4
    end as pos4_agari_synergy_trend5,


      case
        when p1_pos4_agari_synergy is null
         or p2_pos4_agari_synergy is null
         or p3_pos4_agari_synergy is null then null
        else (p3_pos4_agari_synergy - p1_pos4_agari_synergy)::float / 2
      end as pos4_agari_synergy_slope3,
      case
        when p1_pos4_agari_synergy is null
         or p2_pos4_agari_synergy is null
         or p3_pos4_agari_synergy is null then null
        else ((p1_pos4_agari_synergy - p3_pos4_agari_synergy)::float / 2)
          / nullif({{ lag_stddev_sample(['p1_pos4_agari_synergy', 'p2_pos4_agari_synergy', 'p3_pos4_agari_synergy']) }}, 0)
      end as pos4_agari_synergy_trend3_voladj,
      (
        (coalesce(p1_pos4_agari_synergy, 0) + coalesce(p2_pos4_agari_synergy, 0))
        / nullif(
          (case when p1_pos4_agari_synergy is null then 0 else 1 end)
          + (case when p2_pos4_agari_synergy is null then 0 else 1 end),
          0
        )
        -
        (coalesce(p3_pos4_agari_synergy, 0) + coalesce(p4_pos4_agari_synergy, 0) + coalesce(p5_pos4_agari_synergy, 0))
        / nullif(
          (case when p3_pos4_agari_synergy is null then 0 else 1 end)
          + (case when p4_pos4_agari_synergy is null then 0 else 1 end)
          + (case when p5_pos4_agari_synergy is null then 0 else 1 end),
          0
        )
      ) as pos4_agari_synergy_short_long_gap,

      ((coalesce(p1_same_cluster_avg_pos4_agari_synergy, 0) + coalesce(p2_same_cluster_avg_pos4_agari_synergy, 0) + coalesce(p3_same_cluster_avg_pos4_agari_synergy, 0))
      / nullif(
          (case when p1_same_cluster_avg_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p2_same_cluster_avg_pos4_agari_synergy is null then 0 else 1 end)
        + (case when p3_same_cluster_avg_pos4_agari_synergy is null then 0 else 1 end),
        0
      )) as same_cluster_avg_pos4_agari_synergy_avg3,

      case when course_cluster != p1_course_cluster then
        same_cluster_avg_pos4_agari_synergy - p1_same_cluster_avg_pos4_agari_synergy
      else null end as same_cluster_pos4_agari_synergy_diff,

      (coalesce(p1_agari_good, 0) + coalesce(p2_agari_good, 0) + coalesce(p3_agari_good, 0))
      / nullif(
          (case when p1_agari_good is null then 0 else 1 end)
        + (case when p2_agari_good is null then 0 else 1 end)
        + (case when p3_agari_good is null then 0 else 1 end),
        0
      ) as agari_good_avg3,

      (coalesce(p1_ten4f_vs_avg_front_runners, 0) + coalesce(p2_ten4f_vs_avg_front_runners, 0) + coalesce(p3_ten4f_vs_avg_front_runners, 0))
      / nullif(
          (case when p1_ten4f_vs_avg_front_runners is null then 0 else 1 end)
        + (case when p2_ten4f_vs_avg_front_runners is null then 0 else 1 end)
        + (case when p3_ten4f_vs_avg_front_runners is null then 0 else 1 end),
        0
      ) as ten4f_vs_avg_front_runners_avg3,
      (coalesce(p1_running_style_cd, 0) + coalesce(p2_running_style_cd, 0) + coalesce(p3_running_style_cd, 0))::float
      / nullif(
          (case when p1_running_style_cd is null then 0 else 1 end)
        + (case when p2_running_style_cd is null then 0 else 1 end)
        + (case when p3_running_style_cd is null then 0 else 1 end),
        0
      ) as running_style_avg3,

    --直近3走 rel_agari 最小値
    case
      when p1_rel_agari3f is null
       and p2_rel_agari3f is null
       and p3_rel_agari3f is null then null
      else least(
        coalesce(p1_rel_agari3f, 9999),
        coalesce(p2_rel_agari3f, 9999),
        coalesce(p3_rel_agari3f, 9999)
      )
    end as horse_rel_agari3f_min3,
    case
      when p1_rel_agari3f is null
       and p2_rel_agari3f is null
       and p3_rel_agari3f is null
       and p4_rel_agari3f is null
       and p5_rel_agari3f is null then null
      else least(
        coalesce(p1_rel_agari3f, 9999),
        coalesce(p2_rel_agari3f, 9999),
        coalesce(p3_rel_agari3f, 9999),
        coalesce(p4_rel_agari3f, 9999),
        coalesce(p5_rel_agari3f, 9999)
      )
    end as horse_rel_agari3f_min5,
    --time_vs_avg の直近3走最小値
    case
      when p1_time_vs_avg is null
       and p2_time_vs_avg is null
       and p3_time_vs_avg is null then null
      else least(
        coalesce(p1_time_vs_avg, 9999),
        coalesce(p2_time_vs_avg, 9999),
        coalesce(p3_time_vs_avg, 9999)
      )
    end as time_vs_avg_min3,
    case
      when p1_time_vs_avg is null
       and p2_time_vs_avg is null
       and p3_time_vs_avg is null
       and p4_time_vs_avg is null
       and p5_time_vs_avg is null then null
      else least(
        coalesce(p1_time_vs_avg, 9999),
        coalesce(p2_time_vs_avg, 9999),
        coalesce(p3_time_vs_avg, 9999),
        coalesce(p4_time_vs_avg, 9999),
        coalesce(p5_time_vs_avg, 9999)
      )
    end as time_vs_avg_min5,
    case
      when p1_pos4_agari_synergy is null
       and p2_pos4_agari_synergy is null
       and p3_pos4_agari_synergy is null then null
      else greatest(
        coalesce(p1_pos4_agari_synergy, -9999),
        coalesce(p2_pos4_agari_synergy, -9999),
        coalesce(p3_pos4_agari_synergy, -9999)
      )
    end as pos4_agari_synergy_max3,
    case
      when p1_pos4_agari_synergy is null
       and p2_pos4_agari_synergy is null
       and p3_pos4_agari_synergy is null
       and p4_pos4_agari_synergy is null
       and p5_pos4_agari_synergy is null then null
      else greatest(
        coalesce(p1_pos4_agari_synergy, -9999),
        coalesce(p2_pos4_agari_synergy, -9999),
        coalesce(p3_pos4_agari_synergy, -9999),
        coalesce(p4_pos4_agari_synergy, -9999),
        coalesce(p5_pos4_agari_synergy, -9999)
      )
    end as pos4_agari_synergy_max5,
    (coalesce(p1_time_diff_adjusted, 0) + coalesce(p2_time_diff_adjusted, 0) + coalesce(p3_time_diff_adjusted, 0))
      / nullif(
          (case when p1_time_diff_adjusted is null then 0 else 1 end)
        + (case when p2_time_diff_adjusted is null then 0 else 1 end)
        + (case when p3_time_diff_adjusted is null then 0 else 1 end),
        0
      ) as time_diff_adjusted_avg3,
    (coalesce(p1_time_diff_adjusted, 0) + coalesce(p2_time_diff_adjusted, 0) + coalesce(p3_time_diff_adjusted, 0) + coalesce(p4_time_diff_adjusted, 0) + coalesce(p5_time_diff_adjusted, 0))
      / nullif(
          (case when p1_time_diff_adjusted is null then 0 else 1 end)
        + (case when p2_time_diff_adjusted is null then 0 else 1 end)
        + (case when p3_time_diff_adjusted is null then 0 else 1 end)
        + (case when p4_time_diff_adjusted is null then 0 else 1 end)
        + (case when p5_time_diff_adjusted is null then 0 else 1 end),
        0
      ) as time_diff_adjusted_avg5,

      (coalesce(p1_jockey_avg_place_rate, 0) + coalesce(p2_jockey_avg_place_rate, 0) + coalesce(p3_jockey_avg_place_rate, 0))
      / nullif(
          (case when p1_jockey_avg_place_rate is null then 0 else 1 end)
        + (case when p2_jockey_avg_place_rate is null then 0 else 1 end)
        + (case when p3_jockey_avg_place_rate is null then 0 else 1 end),
        0
      ) as jockey_avg_place_rate_avg3,
      (coalesce(p1_jockey_avg_place_rate_smooth, 0) + coalesce(p2_jockey_avg_place_rate_smooth, 0) + coalesce(p3_jockey_avg_place_rate_smooth, 0))
      / nullif(
          (case when p1_jockey_avg_place_rate_smooth is null then 0 else 1 end)
        + (case when p2_jockey_avg_place_rate_smooth is null then 0 else 1 end)
        + (case when p3_jockey_avg_place_rate_smooth is null then 0 else 1 end),
        0
      ) as jockey_avg_place_rate_avg3_smooth,

    race_interval_days,
    p2_race_interval_days,
    -- 叩き判定スコア
    -- case
    --   when race_interval_days is null then null
    --   when p2_race_interval_days is null then null
    --   else
    --     race_interval_days::float / nullif(p2_race_interval_days::float, 0)
    -- end as tataki_score,
    -- case 
    --   when race_interval_days is not null and p2_race_interval_days is not null and p3_race_interval_days is not null then
    --     race_interval_days - ((p2_race_interval_days + p3_race_interval_days)::float / 2)
    --   else null
    -- end as tataki_diff,

    case when is_jockey_change = 1 then
    jockey_avg_place_rate / nullif(p1_jockey_avg_place_rate, 0)
    else null end as jockey_place_rate_diff_ratio,
    case when is_jockey_change = 1 then
    jockey_avg_place_rate_smooth / nullif(p1_jockey_avg_place_rate_smooth, 0)
    else null end as jockey_place_rate_diff_ratio_smooth

  from past_lag w
  {% if is_incremental() %}
    where w.held_date >= current_date - interval '7 days'
  {% endif %}
