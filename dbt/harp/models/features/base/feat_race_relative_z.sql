{{config (
  materialized='incremental',
  on_schema_change='sync_all_columns',
  tags=['feature','main'],
  unique_key=['race_id','kettonum'],
  indexes=[
    {'columns': ['race_id', 'kettonum']}
  ]
)}}

with cur_base as (
  select
    race_id,
    kettonum,
    kinryo,
    kinryo_adj,
    jockey_avg_place_rate,
    jockey_avg_place_rate_smooth,
    jockey_place_rate_3y_logit,
    jockey_place_rate_3y_logit_smooth,
    jockey_cluster_avg_place_rate_corrected,
    jockey_place_rate_3y_smooth,
    jockey_starts_3y,
    age_days
  from {{ ref('feat_race_entry_base') }} f
  {% if is_incremental() %}
     where held_date >= current_date - interval '7 days'
{% endif %}
),

past_lag as (
  select
    *
  from {{ ref('feat_race_entry_past_lag') }}
),

horse_metrics as (
  select
    kettonum,
    held_date,
    same_distance_weighted_avg_pos4_agari_synergy,
    same_turn_direction_surface_avg_pos4_agari_synergy,
    same_homestretch_slope_surface_avg_pos4_agari_synergy,
    same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy
  from {{ ref('feat_horse_past_metrics') }}
),


rank_input as (
  select
    *
  from past_lag pl
  left join cur_base b
    using (race_id, kettonum)
  left join horse_metrics hm
    using (kettonum, held_date)
), 




race_stats as (
  select
    race_id,

    avg(horse_rel_agari3f_avg3)            as rel_agari_avg,
    stddev_pop(horse_rel_agari3f_avg3)     as rel_agari_sd,

    avg(horse_corner4_avg3)                as corner4_avg,
    stddev_pop(horse_corner4_avg3)         as corner4_sd,
    avg(horse_corner4_avg5)                as corner4_avg5_avg,
    stddev_pop(horse_corner4_avg5)         as corner4_avg5_sd,

    avg(time_vs_avg_avg3)                  as time_vs_avg_avg,
    stddev_pop(time_vs_avg_avg3)           as time_vs_avg_sd,
    avg(time_vs_avg_avg5)                  as time_vs_avg_avg5_avg,
    stddev_pop(time_vs_avg_avg5)           as time_vs_avg_avg5_sd,
    avg(time_vs_avg_wavg5_recent)          as time_vs_avg_wavg5_recent_avg,
    stddev_pop(time_vs_avg_wavg5_recent)   as time_vs_avg_wavg5_recent_sd,
    min(time_vs_avg_wavg5_recent)          as time_vs_avg_wavg5_recent_min_in_race,
    avg(time_vs_avg_sd5)                   as time_vs_avg_sd5_avg,
    stddev_pop(time_vs_avg_sd5)            as time_vs_avg_sd5_sd,
    avg(time_vs_avg_trend5)                as time_vs_avg_trend5_avg,
    stddev_pop(time_vs_avg_trend5)         as time_vs_avg_trend5_sd,

    avg(time_vs_pace_avg_avg3)                  as time_vs_pace_avg_avg,
    stddev_pop(time_vs_pace_avg_avg3)           as time_vs_pace_avg_sd,
    avg(time_vs_pace_avg_avg5)                  as time_vs_pace_avg_avg5_avg,
    stddev_pop(time_vs_pace_avg_avg5)           as time_vs_pace_avg_avg5_sd,
    avg(time_vs_pace_avg_wavg5_recent)          as time_vs_pace_avg_wavg5_recent_avg,
    stddev_pop(time_vs_pace_avg_wavg5_recent)   as time_vs_pace_avg_wavg5_recent_sd,

    avg(time_diff_avg3)                    as time_diff_avg,
    stddev_pop(time_diff_avg3)             as time_diff_sd,
    percentile_cont(0.25) within group (order by time_diff_avg3)
                                          as time_diff_q1,
    percentile_cont(0.50) within group (order by time_diff_avg3)
                                          as time_diff_median,
    percentile_cont(0.75) within group (order by time_diff_avg3)
                                          as time_diff_q3,
    avg(time_diff_avg5)                    as time_diff_avg5_avg,
    stddev_pop(time_diff_avg5)             as time_diff_avg5_sd,
    avg(time_diff_wavg5_recent)            as time_diff_wavg5_recent_avg,
    stddev_pop(time_diff_wavg5_recent)     as time_diff_wavg5_recent_sd,
    min(time_diff_wavg5_recent)            as time_diff_wavg5_recent_min_in_race,
    percentile_cont(0.25) within group (order by time_diff_wavg5_recent)
                                          as time_diff_wavg5_recent_q1,
    percentile_cont(0.50) within group (order by time_diff_wavg5_recent)
                                          as time_diff_wavg5_recent_median,
    percentile_cont(0.75) within group (order by time_diff_wavg5_recent)
                                          as time_diff_wavg5_recent_q3,
    avg(time_diff_sd5)                     as time_diff_sd5_avg,
    stddev_pop(time_diff_sd5)              as time_diff_sd5_sd,
    avg(time_diff_trend5)                  as time_diff_trend5_avg,
    stddev_pop(time_diff_trend5)           as time_diff_trend5_sd,

    avg(pos4_agari_synergy_avg3)           as pos4_agari_synergy_avg,
    stddev_pop(pos4_agari_synergy_avg3)    as pos4_agari_synergy_sd,
    max(pos4_agari_synergy_avg3)           as pos4_agari_synergy_max_in_race,
    avg(pos4_agari_synergy_avg5)           as pos4_agari_synergy_avg5_avg,
    stddev_pop(pos4_agari_synergy_avg5)    as pos4_agari_synergy_avg5_sd,
    avg(pos4_agari_synergy_wavg5_recent)   as pos4_agari_synergy_wavg5_recent_avg,
    stddev_pop(pos4_agari_synergy_wavg5_recent) as pos4_agari_synergy_wavg5_recent_sd,
    max(pos4_agari_synergy_wavg5_recent)   as pos4_agari_synergy_wavg5_recent_max_in_race,
    percentile_cont(0.25) within group (order by pos4_agari_synergy_wavg5_recent)
                                          as pos4_agari_synergy_wavg5_recent_q1,
    percentile_cont(0.50) within group (order by pos4_agari_synergy_wavg5_recent)
                                          as pos4_agari_synergy_wavg5_recent_median,
    percentile_cont(0.75) within group (order by pos4_agari_synergy_wavg5_recent)
                                          as pos4_agari_synergy_wavg5_recent_q3,
    avg(pos4_agari_synergy_sd5)            as pos4_agari_synergy_sd5_avg,
    stddev_pop(pos4_agari_synergy_sd5)     as pos4_agari_synergy_sd5_sd,
    avg(pos4_agari_synergy_trend5)         as pos4_agari_synergy_trend5_avg,
    stddev_pop(pos4_agari_synergy_trend5)  as pos4_agari_synergy_trend5_sd,
    avg(pos4_agari_synergy_max3)           as pos4_agari_synergy_max,
    stddev_pop(pos4_agari_synergy_max3)    as pos4_agari_synergy_max_sd,

    avg(agari_good_avg3)                   as agari_good_avg,
    stddev_pop(agari_good_avg3)            as agari_good_sd,

    avg(same_cluster_avg_pos4_agari_synergy)           as same_cluster_avg_pos4_agari_synergy_avg,
    stddev_pop(same_cluster_avg_pos4_agari_synergy)    as same_cluster_avg_pos4_agari_synergy_sd,
    avg(same_distance_weighted_avg_pos4_agari_synergy) as same_distance_weighted_avg_pos4_agari_synergy_avg,
    stddev_pop(same_distance_weighted_avg_pos4_agari_synergy) as same_distance_weighted_avg_pos4_agari_synergy_sd,
    avg(same_turn_direction_surface_avg_pos4_agari_synergy) as same_turn_direction_surface_avg_pos4_agari_synergy_avg,
    stddev_pop(same_turn_direction_surface_avg_pos4_agari_synergy) as same_turn_direction_surface_avg_pos4_agari_synergy_sd,
    avg(same_homestretch_slope_surface_avg_pos4_agari_synergy) as same_homestretch_slope_surface_avg_pos4_agari_synergy_avg,
    stddev_pop(same_homestretch_slope_surface_avg_pos4_agari_synergy) as same_homestretch_slope_surface_avg_pos4_agari_synergy_sd,
    avg(same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy) as same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_avg,
    stddev_pop(same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy) as same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_sd,

    avg(horse_rel_agari3f_min3)            as rel_agari_min_avg,
    stddev_pop(horse_rel_agari3f_min3)     as rel_agari_min_sd,

    avg(time_vs_avg_min3)                  as time_vs_avg_min,
    stddev_pop(time_vs_avg_min3)           as time_vs_avg_min_sd,
    min(time_vs_avg_min3)                  as time_vs_avg_min_in_race,

    avg(time_vs_avg_adjusted_avg3)           as time_vs_avg_adjusted_avg,
    stddev_pop(time_vs_avg_adjusted_avg3)    as time_vs_avg_adjusted_sd,
    min(time_vs_avg_adjusted_avg3)           as time_vs_avg_adjusted_min_in_race,
    avg(time_vs_avg_adjusted_avg5)           as time_vs_avg_adjusted_avg5_avg,
    stddev_pop(time_vs_avg_adjusted_avg5)    as time_vs_avg_adjusted_avg5_sd,
    avg(time_vs_avg_adjusted_wavg5_recent)   as time_vs_avg_adjusted_wavg5_recent_avg,
    stddev_pop(time_vs_avg_adjusted_wavg5_recent) as time_vs_avg_adjusted_wavg5_recent_sd,
    min(time_vs_avg_adjusted_wavg5_recent)   as time_vs_avg_adjusted_wavg5_recent_min_in_race,

    avg(time_diff_adjusted_avg3)           as time_diff_adjusted_avg,
    stddev_pop(time_diff_adjusted_avg3)    as time_diff_adjusted_sd,
    avg(time_diff_adjusted_avg5)           as time_diff_adjusted_avg5_avg,
    stddev_pop(time_diff_adjusted_avg5)    as time_diff_adjusted_avg5_sd,
    avg(kinryo) as avg_kinryo,
    stddev_pop(kinryo) as stddev_kinryo,
    avg(kinryo_adj) as avg_kinryo_adj,
    stddev_pop(kinryo_adj) as stddev_kinryo_adj,
    sum(case when running_style_avg3 <= 1.5 then 1 else 0 end) as num_front_runners,
    avg(ten4f_vs_avg_front_runners_avg3) as avg_ten4f_vs_avg_front_runners_avg3,
    stddev_pop(ten4f_vs_avg_front_runners_avg3) as stddev_ten4f_vs_avg_front_runners_avg3,
    min(ten4f_vs_avg_front_runners_avg3) as min_ten4f_vs_avg_front_runners_avg3,
    avg(jockey_avg_place_rate) as avg_jockey_place_rate_in_race,
    stddev_pop(jockey_avg_place_rate) as stddev_jockey_place_rate_in_race,
    avg(jockey_avg_place_rate_smooth) as avg_jockey_place_rate_in_race_smooth,
    stddev_pop(jockey_avg_place_rate_smooth) as stddev_jockey_place_rate_in_race_smooth,
    avg(jockey_place_rate_3y_logit) as avg_jockey_place_rate_3y_logit_in_race,
    stddev_pop(jockey_place_rate_3y_logit) as stddev_jockey_place_rate_3y_logit_in_race,
    avg(jockey_place_rate_3y_logit_smooth) as avg_jockey_place_rate_3y_logit_in_race_smooth,
    stddev_pop(jockey_place_rate_3y_logit_smooth) as stddev_jockey_place_rate_3y_logit_in_race_smooth,
    avg(
      case
        when jockey_cluster_avg_place_rate_corrected is null then null
        else
          ln(
            least(greatest(jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6)
            / (1 - least(greatest(jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6))
          )
      end
    ) as avg_jockey_cluster_avg_place_rate_corrected_logit_in_race,
    stddev_pop(
      case
        when jockey_cluster_avg_place_rate_corrected is null then null
        else
          ln(
            least(greatest(jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6)
            / (1 - least(greatest(jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6))
          )
      end
    ) as stddev_jockey_cluster_avg_place_rate_corrected_logit_in_race,
    avg(same_cluster_avg_pos4_agari_synergy_avg3) as avg_same_cluster_avg_pos4_agari_synergy_avg3,
    stddev_pop(same_cluster_avg_pos4_agari_synergy_avg3) as stddev_same_cluster_avg_pos4_agari_synergy_avg3,
    
    avg(age_days) as avg_age_days,
    stddev_pop(age_days) as stddev_age_days

  from rank_input
  group by race_id
)

select
  pl.race_id,
  pl.kettonum,
  pl.is_shokyu,
  pl.race_level_diff,
  pl.p1_race_level,
  pl.is_jockey_change,
  pl.distance_change,
  pl.p1_distance_m,
  pl.is_surface_changed,
  pl.course_cluster_change,
  pl.race_interval_days,
  pl.p2_race_interval_days,
  pl.horse_corner4_avg3,
  pl.horse_corner4_avg5,
  pl.horse_corner4_wavg5_recent,
  pl.horse_corner4_sd5,
  pl.horse_corner4_trend5,
  s.pos4_agari_synergy_sd,
  pl.horse_rel_agari3f_avg3,
  pl.agari3f_rank_avg3,
  pl.agari3f_rank_percentile_avg3,
  pl.horse_rel_agari3f_avg5,
  pl.horse_rel_agari3f_wavg5_recent,
  pl.pos4_agari_synergy_avg3,
  pl.pos4_agari_synergy_avg5,
  pl.pos4_agari_synergy_wavg5_recent,
  pl.pos4_agari_synergy_sd5,
  pl.pos4_agari_synergy_trend5,
  pl.p1_pos4_agari_synergy,
  pl.p2_pos4_agari_synergy,
  pl.p3_pos4_agari_synergy,
     pl.p1_time_diff,
     pl.p2_time_diff,
     pl.p3_time_diff,
     pl.p1_ten3f_vs_avg,
     pl.p2_ten3f_vs_avg,
  pl.p3_ten3f_vs_avg,
  pl.ten3f_vs_avg_avg3,
  pl.p1_pace_front_disadvantage,
  pl.p2_pace_front_disadvantage,
  pl.p3_pace_front_disadvantage,
  pl.pace_front_disadvantage_avg3,
     pl.p1_time_vs_pace_avg,
     pl.p2_time_vs_pace_avg,
  pl.p3_time_vs_pace_avg,
  pl.time_diff_avg3,
  pl.time_diff_avg5,
  pl.time_diff_wavg5_recent,
  pl.time_diff_sd5,
  pl.time_diff_trend5,
  pl.time_vs_pace_avg_avg3,
  pl.time_vs_pace_avg_avg5,
  pl.time_vs_pace_avg_wavg5_recent,
  pl.time_vs_avg_avg5,
  pl.time_vs_avg_wavg5_recent,
  pl.time_vs_avg_sd5,
  pl.time_vs_avg_trend5,
  pl.time_vs_avg_adjusted_avg5,
  pl.time_vs_avg_adjusted_wavg5_recent,
  pl.time_diff_adjusted_avg5,
  s.time_vs_avg_sd,
  pl.p1_corner4,
  pl.p2_corner4,
  pl.p3_corner4,
  pl.horse_corner4_sd3,
  pl.horse_kinryo_avg3,
  pl.pos4_agari_synergy_slope3,
  pl.pos4_agari_synergy_trend3_voladj,
  pl.pos4_agari_synergy_short_long_gap,
  pl.same_cluster_avg_pos4_agari_synergy_avg3,
  pl.p1_weight,
  pl.p1_weight_change,
  pl.weight_change_ratio,
  pl.condition_change_score,
  pl.distance_change_score,
  pl.surface_change_score,
  pl.jockey_place_rate_diff_ratio,
  pl.jockey_place_rate_diff_ratio_smooth,
  running_style_avg3,
  round(running_style_avg3)::int as running_style,
  pl.same_cluster_pos4_agari_synergy_diff,
  b.jockey_place_rate_3y_smooth,
  pl.p1_wood_lap_time_1,
  pl.p1_wood_lap_time_1_z_tozai_day,
  pl.p1_trainer_wood_lap_time_1_fast_excess_z_3y,
  pl.p1_hanro_lap_time_1,
  pl.p1_hanro_lap_time_1_z_tozai_day,
  pl.p1_trainer_hanro_lap_time_1_fast_excess_z_3y,
  pl.jockey_avg_place_rate_avg3,
  pl.jockey_avg_place_rate_avg3_smooth,
  pl.num_past3_races,
  pl.num_past5_races,
  pl.course_cluster_change_score,
  pl.p1_course_cluster,
  pl.p1_jyo_cd,
  pl.blinker_added,

  s.num_front_runners,
  s.avg_ten4f_vs_avg_front_runners_avg3 as pace_front_runners_avg,
  s.min_ten4f_vs_avg_front_runners_avg3 as pace_front_runners_min,

  case when pl.horse_rel_agari3f_avg3 is null then null
       else (pl.horse_rel_agari3f_avg3 - s.rel_agari_avg) / nullif(s.rel_agari_sd, 0) end as rel_agari_z,

  case when pl.horse_corner4_avg3 is null then null
       else (pl.horse_corner4_avg3 - s.corner4_avg) / nullif(s.corner4_sd, 0) end as corner4_rate_z,
  case when pl.horse_corner4_avg5 is null then null
       else (pl.horse_corner4_avg5 - s.corner4_avg5_avg) / nullif(s.corner4_avg5_sd, 0) end as corner4_rate_avg5_z,
  case when pl.horse_corner4_trend5 is null then null
       else (pl.horse_corner4_trend5 - avg(pl.horse_corner4_trend5) over (partition by pl.race_id))
            / nullif(stddev_pop(pl.horse_corner4_trend5) over (partition by pl.race_id), 0) end as corner4_trend5_z,



  s.corner4_avg as race_avg_corner4,
  s.corner4_sd as race_stddev_corner4,
  s.corner4_avg - 0.5 as race_styele_score,
  pl.horse_corner4_avg3 - s.corner4_avg as horse_styele_diff,
  -(s.corner4_avg - 0.5 ) * (pl.horse_corner4_avg3 - s.corner4_avg) as style_score,


  case when pl.time_vs_avg_avg3 is null then null
       else (pl.time_vs_avg_avg3 - s.time_vs_avg_avg) / nullif(s.time_vs_avg_sd, 0) end as time_vs_avg_z,
  case when pl.time_vs_avg_avg5 is null then null
       else (pl.time_vs_avg_avg5 - s.time_vs_avg_avg5_avg) / nullif(s.time_vs_avg_avg5_sd, 0) end as time_vs_avg_avg5_z,
  case when pl.time_vs_avg_wavg5_recent is null then null
       else (pl.time_vs_avg_wavg5_recent - s.time_vs_avg_wavg5_recent_avg) / nullif(s.time_vs_avg_wavg5_recent_sd, 0) end as time_vs_avg_wavg5_recent_z,
  pl.time_vs_avg_wavg5_recent - s.time_vs_avg_wavg5_recent_min_in_race as time_vs_avg_wavg5_recent_diff_top_in_race,
  case when pl.time_vs_avg_sd5 is null then null
       else (pl.time_vs_avg_sd5 - s.time_vs_avg_sd5_avg) / nullif(s.time_vs_avg_sd5_sd, 0) end as time_vs_avg_sd5_z,
  case when pl.time_vs_avg_trend5 is null then null
       else (pl.time_vs_avg_trend5 - s.time_vs_avg_trend5_avg) / nullif(s.time_vs_avg_trend5_sd, 0) end as time_vs_avg_trend5_z,

  case when pl.time_vs_pace_avg_avg3 is null then null
       else (pl.time_vs_pace_avg_avg3 - s.time_vs_pace_avg_avg) / nullif(s.time_vs_pace_avg_sd, 0) end as time_vs_pace_avg_z,
  case when pl.time_vs_pace_avg_avg5 is null then null
       else (pl.time_vs_pace_avg_avg5 - s.time_vs_pace_avg_avg5_avg) / nullif(s.time_vs_pace_avg_avg5_sd, 0) end as time_vs_pace_avg_avg5_z,
  case when pl.time_vs_pace_avg_wavg5_recent is null then null
       else (pl.time_vs_pace_avg_wavg5_recent - s.time_vs_pace_avg_wavg5_recent_avg) / nullif(s.time_vs_pace_avg_wavg5_recent_sd, 0) end as time_vs_pace_avg_wavg5_recent_z,

  pl.time_vs_avg_avg3  - s.time_vs_avg_min_in_race as time_vs_avg_diff_top_in_race,

  case when pl.time_vs_avg_adjusted_avg3 is null then null
       else (pl.time_vs_avg_adjusted_avg3 - s.time_vs_avg_adjusted_avg) / nullif(s.time_vs_avg_adjusted_sd, 0) end as time_vs_avg_adjusted_z,
  case when pl.time_vs_avg_adjusted_avg5 is null then null
       else (pl.time_vs_avg_adjusted_avg5 - s.time_vs_avg_adjusted_avg5_avg) / nullif(s.time_vs_avg_adjusted_avg5_sd, 0) end as time_vs_avg_adjusted_avg5_z,
  case when pl.time_vs_avg_adjusted_wavg5_recent is null then null
       else (pl.time_vs_avg_adjusted_wavg5_recent - s.time_vs_avg_adjusted_wavg5_recent_avg) / nullif(s.time_vs_avg_adjusted_wavg5_recent_sd, 0) end as time_vs_avg_adjusted_wavg5_recent_z,
  pl.time_vs_avg_adjusted_wavg5_recent - s.time_vs_avg_adjusted_wavg5_recent_min_in_race as time_vs_avg_adjusted_wavg5_recent_diff_top_in_race,

  pl.time_vs_avg_adjusted_avg3  - s.time_vs_avg_adjusted_min_in_race as time_vs_avg_adjusted_diff_top_in_race,

  case when pl.time_diff_avg3 is null then null
       else (pl.time_diff_avg3 - s.time_diff_avg) / nullif(s.time_diff_sd, 0) end as time_diff_z,
  case when pl.time_diff_avg3 is null then null
       else (pl.time_diff_avg3 - s.time_diff_median)
            / nullif(s.time_diff_q3 - s.time_diff_q1, 0) end as time_diff_robust,
  case when pl.time_diff_avg5 is null then null
       else (pl.time_diff_avg5 - s.time_diff_avg5_avg) / nullif(s.time_diff_avg5_sd, 0) end as time_diff_avg5_z,
  case when pl.time_diff_wavg5_recent is null then null
       else (pl.time_diff_wavg5_recent - s.time_diff_wavg5_recent_avg) / nullif(s.time_diff_wavg5_recent_sd, 0) end as time_diff_wavg5_recent_z,
  case when pl.time_diff_wavg5_recent is null then null
       else (pl.time_diff_wavg5_recent - s.time_diff_wavg5_recent_median)
            / nullif(s.time_diff_wavg5_recent_q3 - s.time_diff_wavg5_recent_q1, 0) end as time_diff_wavg5_recent_robust,
  pl.time_diff_wavg5_recent - s.time_diff_wavg5_recent_min_in_race as time_diff_wavg5_recent_diff_top_in_race,
  rank() over (partition by pl.race_id order by pl.time_diff_wavg5_recent asc nulls last) as time_diff_wavg5_recent_rank,
  case when pl.time_diff_sd5 is null then null
       else (pl.time_diff_sd5 - s.time_diff_sd5_avg) / nullif(s.time_diff_sd5_sd, 0) end as time_diff_sd5_z,
  case when pl.time_diff_trend5 is null then null
       else (pl.time_diff_trend5 - s.time_diff_trend5_avg) / nullif(s.time_diff_trend5_sd, 0) end as time_diff_trend5_z,

  (rank() over (partition by pl.race_id order by pl.time_diff_avg3))  as time_diff_rank,

  case when pl.pos4_agari_synergy_avg3 is null then null
       else (pl.pos4_agari_synergy_avg3 - s.pos4_agari_synergy_avg) / nullif(s.pos4_agari_synergy_sd, 0) end as pos4_agari_synergy_z,
  case when pl.pos4_agari_synergy_avg5 is null then null
       else (pl.pos4_agari_synergy_avg5 - s.pos4_agari_synergy_avg5_avg) / nullif(s.pos4_agari_synergy_avg5_sd, 0) end as pos4_agari_synergy_avg5_z,
  case when pl.pos4_agari_synergy_wavg5_recent is null then null
       else (pl.pos4_agari_synergy_wavg5_recent - s.pos4_agari_synergy_wavg5_recent_avg) / nullif(s.pos4_agari_synergy_wavg5_recent_sd, 0) end as pos4_agari_synergy_wavg5_recent_z,
  s.pos4_agari_synergy_wavg5_recent_median as race_pos4_agari_synergy_wavg5_recent_median,
  s.pos4_agari_synergy_wavg5_recent_q3 - s.pos4_agari_synergy_wavg5_recent_q1 as race_pos4_agari_synergy_wavg5_recent_iqr,
  case when pl.pos4_agari_synergy_wavg5_recent is null then null
       else (pl.pos4_agari_synergy_wavg5_recent - s.pos4_agari_synergy_wavg5_recent_median)
            / nullif(s.pos4_agari_synergy_wavg5_recent_q3 - s.pos4_agari_synergy_wavg5_recent_q1, 0) end as pos4_agari_synergy_wavg5_recent_robust,
  pl.pos4_agari_synergy_wavg5_recent - s.pos4_agari_synergy_wavg5_recent_max_in_race as pos4_agari_synergy_wavg5_recent_diff_top_in_race,
  case when pl.pos4_agari_synergy_sd5 is null then null
       else (pl.pos4_agari_synergy_sd5 - s.pos4_agari_synergy_sd5_avg) / nullif(s.pos4_agari_synergy_sd5_sd, 0) end as pos4_agari_synergy_sd5_z,
  case when pl.pos4_agari_synergy_trend5 is null then null
       else (pl.pos4_agari_synergy_trend5 - s.pos4_agari_synergy_trend5_avg) / nullif(s.pos4_agari_synergy_trend5_sd, 0) end as pos4_agari_synergy_trend5_z,
  pl.pos4_agari_synergy_avg3 - s.pos4_agari_synergy_max_in_race as pos4_agari_synergy_diff_top_in_race,

  case when pl.pos4_agari_synergy_max3 is null then null
       else (pl.pos4_agari_synergy_max3 - s.pos4_agari_synergy_max) / nullif(s.pos4_agari_synergy_max_sd, 0) end as pos4_agari_synergy_max_z,

  case when pl.agari_good_avg3 is null then null
       else (pl.agari_good_avg3 - s.agari_good_avg) / nullif(s.agari_good_sd, 0) end as agari_good_z,

  case when pl.horse_rel_agari3f_min3 is null then null
       else (pl.horse_rel_agari3f_min3 - s.rel_agari_min_avg) / nullif(s.rel_agari_min_sd, 0) end as rel_agari_min_z,

  case when pl.same_cluster_avg_pos4_agari_synergy is null then null
       else (pl.same_cluster_avg_pos4_agari_synergy - s.same_cluster_avg_pos4_agari_synergy_avg) / nullif(s.same_cluster_avg_pos4_agari_synergy_sd, 0) end as same_cluster_avg_pos4_agari_synergy_z,
  case when hm.same_turn_direction_surface_avg_pos4_agari_synergy is null then null
       else (hm.same_turn_direction_surface_avg_pos4_agari_synergy - s.same_turn_direction_surface_avg_pos4_agari_synergy_avg)
            / nullif(s.same_turn_direction_surface_avg_pos4_agari_synergy_sd, 0) end as same_turn_direction_surface_avg_pos4_agari_synergy_z,
  case when hm.same_homestretch_slope_surface_avg_pos4_agari_synergy is null then null
       else (hm.same_homestretch_slope_surface_avg_pos4_agari_synergy - s.same_homestretch_slope_surface_avg_pos4_agari_synergy_avg)
            / nullif(s.same_homestretch_slope_surface_avg_pos4_agari_synergy_sd, 0) end as same_homestretch_slope_surface_avg_pos4_agari_synergy_z,
  case when hm.same_distance_weighted_avg_pos4_agari_synergy is null then null
       else (hm.same_distance_weighted_avg_pos4_agari_synergy - s.same_distance_weighted_avg_pos4_agari_synergy_avg)
            / nullif(s.same_distance_weighted_avg_pos4_agari_synergy_sd, 0) end as same_distance_weighted_avg_pos4_agari_synergy_z,
  case when hm.same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy is null then null
       else (hm.same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy - s.same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_avg)
            / nullif(s.same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_sd, 0) end as same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_z,

  rank() over (partition by pl.race_id order by pl.same_cluster_avg_pos4_agari_synergy desc nulls last) as same_cluster_avg_pos4_agari_synergy_rank,

  case when pl.time_vs_avg_min3 is null then null
       else (pl.time_vs_avg_min3 - s.time_vs_avg_min) / nullif(s.time_vs_avg_min_sd, 0) end as time_vs_avg_min_z,

  case when pl.time_diff_adjusted_avg3 is null then null
       else (pl.time_diff_adjusted_avg3 - s.time_diff_adjusted_avg) / nullif(s.time_diff_adjusted_sd, 0) end as time_diff_adjusted_z,
  case when pl.time_diff_adjusted_avg5 is null then null
       else (pl.time_diff_adjusted_avg5 - s.time_diff_adjusted_avg5_avg) / nullif(s.time_diff_adjusted_avg5_sd, 0) end as time_diff_adjusted_avg5_z,

  case when b.jockey_avg_place_rate is null then null
       else (b.jockey_avg_place_rate - s.avg_jockey_place_rate_in_race) / nullif(s.stddev_jockey_place_rate_in_race, 0) end as jockey_place_rate_z,
  case when b.jockey_avg_place_rate_smooth is null then null
       else (b.jockey_avg_place_rate_smooth - s.avg_jockey_place_rate_in_race_smooth) / nullif(s.stddev_jockey_place_rate_in_race_smooth, 0) end as jockey_place_rate_z_smooth,
  case when b.jockey_place_rate_3y_logit is null then null
       else (b.jockey_place_rate_3y_logit - s.avg_jockey_place_rate_3y_logit_in_race) / nullif(s.stddev_jockey_place_rate_3y_logit_in_race, 0) end as jockey_place_rate_3y_logit_z,
  case when b.jockey_place_rate_3y_logit_smooth is null then null
       else (b.jockey_place_rate_3y_logit_smooth - s.avg_jockey_place_rate_3y_logit_in_race_smooth) / nullif(s.stddev_jockey_place_rate_3y_logit_in_race_smooth, 0) end as jockey_place_rate_3y_logit_z_smooth,
  case when b.jockey_cluster_avg_place_rate_corrected is null then null
       else (
         ln(
           least(greatest(b.jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6)
           / (1 - least(greatest(b.jockey_cluster_avg_place_rate_corrected, 1e-6), 1 - 1e-6))
         )
         - s.avg_jockey_cluster_avg_place_rate_corrected_logit_in_race
       ) / nullif(s.stddev_jockey_cluster_avg_place_rate_corrected_logit_in_race, 0) end as jockey_cluster_avg_place_rate_corrected_logit_z,
  case when b.jockey_cluster_avg_place_rate_corrected is null then null
       else rank() over (partition by pl.race_id order by b.jockey_cluster_avg_place_rate_corrected desc nulls last) end as jockey_cluster_avg_place_rate_corrected_rank,

   s.avg_jockey_place_rate_in_race as race_avg_jockey_place_rate,
   s.avg_jockey_place_rate_in_race_smooth as race_avg_jockey_place_rate_smooth,

  case when pl.same_cluster_avg_pos4_agari_synergy_avg3 is null then null
       else (pl.same_cluster_avg_pos4_agari_synergy_avg3 - s.avg_same_cluster_avg_pos4_agari_synergy_avg3) / nullif(s.stddev_same_cluster_avg_pos4_agari_synergy_avg3, 0) end as past_same_cluster_avg_pos4_as_z,
  -- 斤量ｚ
   case
      when kinryo is null then null
        else (kinryo - s.avg_kinryo) / nullif(s.stddev_kinryo, 0) end as kinryo_z,
  -- 斤量調整ｚ
   case
      when kinryo_adj is null then null
        else (kinryo_adj - s.avg_kinryo_adj) / nullif(s.stddev_kinryo_adj, 0) end as kinryo_adj_z,
  
  case when age_days is null then null
       else (age_days - s.avg_age_days) / nullif(s.stddev_age_days, 0) end as age_days_z
from past_lag  pl
left join race_stats s
  using (race_id)
left join cur_base b
  using (race_id, kettonum)
left join horse_metrics hm
  using (kettonum, held_date)
{% if is_incremental() %}
     where pl.held_date >= current_date - interval '7 days'
{% endif %}
