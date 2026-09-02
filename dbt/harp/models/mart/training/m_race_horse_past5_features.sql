{{config(
  materialized='incremental',
  on_schema_change='sync_all_columns',
  unique_key=['race_id', 'kettonum'],
  tags=['mart','main','feature_inputs']
) }}
with sire_metrics as (
  select
    race_id,
    kettonum,
    sire_starts_5y,
    sire_career_months,
    sire_is_early_phase_3y,
    sire_avg_place_rate,
    same_cluster_sire_past_starts,
    same_cluster_sire_avg_place_rate_smooth,
    same_cluster_sire_avg_pos4_agari_synergy,
    same_cluster_sire_avg_pos4_agari_synergy_diff,
    same_cluster_sire_avg_place_rate,
    same_cluster_sire_avg_diff_logit,
    same_age_sire_past_starts,
    same_age_sire_avg_place_rate_smooth,
    same_age_sire_avg_pos4_agari_synergy,
    same_age_sire_avg_place_rate,
    same_old_cd_sire_past_starts,
    same_old_cd_sire_avg_place_rate_smooth,
    same_old_cd_sire_avg_pos4_agari_synergy,
    same_old_cd_sire_avg_place_rate,
    same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd,
    same_sex_cd_sire_avg_pos4_agari_synergy,
    same_weight_sire_past_starts,
    same_weight_sire_place_rate_5y as same_weight_sire_place_rate,
    same_weight_sire_place_rate_5y_smooth as same_weight_sire_place_rate_smooth,
    same_surface_dist_pm200_sire_past_starts,
    same_surface_dist_pm200_sire_avg_place_rate,
    same_surface_dist_pm200_sire_avg_pos4_agari_synergy,
    same_surface_dist_pm200_sire_avg_place_rate_smooth,
    sire_avg_place_rate_smooth,
    sire_avg_pos4_agari_synergy,
    sire_avg_time_diff,
    same_age_sire_avg_place_rate_smooth_prev_age,
    same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,
    same_surface_dist_pm200_sire_avg_diff
  from {{ ref('feat_sire_metrics') }}
),

dam_metrics as (
  select
    race_id,
    kettonum,
    dam_starts_5y,
    dam_avg_place_rate,
    dam_avg_place_rate_smooth,
    dam_avg_pos4_agari_synergy,
    dam_avg_time_diff,
    same_cluster_dam_past_starts,
    same_cluster_dam_avg_place_rate,
    same_cluster_dam_avg_place_rate_smooth,
    same_cluster_dam_avg_pos4_agari_synergy
  from {{ ref('feat_dam_metrics') }}
),

damsire_metrics as (
  select
    race_id,
    kettonum,
    damsire_starts_5y,
    damsire_avg_place_rate,
    damsire_avg_place_rate_smooth,
    damsire_avg_pos4_agari_synergy,
    damsire_avg_time_diff,
    same_cluster_damsire_past_starts,
    same_cluster_damsire_avg_place_rate,
    same_cluster_damsire_avg_place_rate_smooth,
    same_cluster_damsire_avg_pos4_agari_synergy
  from {{ ref('feat_damsire_metrics') }}
),

horse_past_metrics as (
  select
    kettonum,
    held_date,
    -- active in apps/analysis/src/features/features*.py
    same_cluster_past_starts,
    same_cluster_first_start_flag,
    same_cluster_past_places,
    same_cluster_past_weighted_starts,
    same_cluster_past_weighted_pos4_agari_synergy,
    same_cluster_avg_pos4_agari_synergy,
    same_distance_past_starts,
    same_distance_past_weighted_places,
    same_distance_weighted_avg_pos4_agari_synergy,
    same_surface_condition_avg_pos4_agari_synergy,
    same_turn_direction_avg_pos4_agari_synergy,
    same_turn_direction_surface_past_starts,
    same_turn_direction_surface_avg_pos4_agari_synergy,
    same_homestretch_slope_surface_past_starts,
    same_homestretch_slope_surface_avg_pos4_agari_synergy,
    same_homestretch_slope_surface_weighted_avg_pos4_agari_synergy as same_homestretch_slope_surface_wavg_pos4_agari_synergy,
    same_straight_distance_bucket_surface_past_starts,
    same_straight_distance_bucket_surface_avg_pos4_agari_synergy,
    same_straight_distance_bucket_surface_weighted_avg_pos4_agari_synergy as same_straight_distance_bucket_surface_wavg_pos4_agari_synergy,
    pace_ntile1_place_rate,
    pace_ntile2_place_rate,
    pace_ntile3_place_rate,
    past_starts,
    past_places

    -- currently unused in apps/analysis/src/features/features*.py
    -- same_cluster_past_time_diffs,
    -- same_cluster_past_pos4_agari_synergy,
    -- same_cluster_past_weighted_places,
    -- same_cluster_past_weighted_time_diffs,
    -- same_cluster_avg_time_diffs,
    -- same_cluster_place_rate,
    -- same_distance_past_places,
    -- same_distance_past_pos4_agari_synergy,
    -- same_distance_past_weighted_starts,
    -- same_distance_past_weighted_pos4_agari_synergy,
    -- same_distance_avg_pos4_agari_synergy,
    -- same_distance_place_rate,
    -- same_distance_weighted_place_rate,
    -- same_surface_condition_past_starts,
    -- same_surface_condition_past_places,
    -- same_surface_condition_past_pos4_agari_synergy,
    -- same_surface_condition_past_weighted_starts,
    -- same_surface_condition_past_weighted_places,
    -- same_surface_condition_past_weighted_pos4_agari_synergy,
    -- same_surface_condition_weighted_avg_pos4_agari_synergy,
    -- same_surface_condition_place_rate,
    -- same_surface_condition_weighted_place_rate,
    -- same_turn_direction_past_starts,
    -- same_turn_direction_past_places,
    -- same_turn_direction_past_pos4_agari_synergy,
    -- same_turn_direction_past_weighted_starts,
    -- same_turn_direction_past_weighted_places,
    -- same_turn_direction_past_weighted_pos4_agari_synergy,
    -- same_turn_direction_weighted_avg_pos4_agari_synergy,
    -- same_turn_direction_place_rate,
    -- same_turn_direction_weighted_place_rate,
    -- same_turn_direction_surface_past_places,
    -- same_turn_direction_surface_past_pos4_agari_synergy,
    -- same_turn_direction_surface_past_weighted_starts,
    -- same_turn_direction_surface_past_weighted_places,
    -- same_turn_direction_surface_past_weighted_pos4_agari_synergy,
    -- same_turn_direction_surface_weighted_avg_pos4_agari_synergy,
    -- same_turn_direction_surface_place_rate,
    -- same_turn_direction_surface_weighted_place_rate,
    -- same_homestretch_slope_surface_past_places,
    -- same_homestretch_slope_surface_past_pos4_agari_synergy,
    -- same_homestretch_slope_surface_past_weighted_starts,
    -- same_homestretch_slope_surface_past_weighted_places,
    -- same_homestretch_slope_surface_past_weighted_pos4_agari_synergy,
    -- same_homestretch_slope_surface_place_rate,
    -- same_homestretch_slope_surface_weighted_place_rate,
    -- same_straight_distance_bucket_surface_past_places,
    -- same_straight_distance_bucket_surface_past_pos4_agari_synergy,
    -- same_straight_distance_bucket_surface_past_weighted_starts,
    -- same_straight_distance_bucket_surface_past_weighted_places,
    -- same_straight_distance_bucket_surface_past_weighted_pos4_agari_synergy,
    -- same_straight_distance_bucket_surface_place_rate,
    -- same_straight_distance_bucket_surface_weighted_place_rate,
    -- same_jyo_distance_past_starts,
    -- same_jyo_distance_past_places,
    -- same_jyo_distance_past_pos4_agari_synergy,
    -- same_jyo_distance_past_weighted_starts,
    -- same_jyo_distance_past_weighted_places,
    -- same_jyo_distance_past_weighted_pos4_agari_synergy,
    -- same_jyo_distance_avg_pos4_agari_synergy,
    -- same_jyo_distance_weighted_avg_pos4_agari_synergy,
    -- same_jyo_distance_place_rate,
    -- same_jyo_distance_weighted_place_rate,
    -- pace_ntile1_past_starts,
    -- pace_ntile1_past_places,
    -- pace_ntile1_past_pos4_agari_synergy,
    -- pace_ntile1_past_weighted_starts,
    -- pace_ntile1_past_weighted_places,
    -- pace_ntile1_past_weighted_pos4_agari_synergy,
    -- pace_ntile1_avg_pos4_agari_synergy,
    -- pace_ntile1_weighted_avg_pos4_agari_synergy,
    -- pace_ntile1_weighted_place_rate,
    -- pace_ntile2_past_starts,
    -- pace_ntile2_past_places,
    -- pace_ntile2_past_pos4_agari_synergy,
    -- pace_ntile2_past_weighted_starts,
    -- pace_ntile2_past_weighted_places,
    -- pace_ntile2_past_weighted_pos4_agari_synergy,
    -- pace_ntile2_avg_pos4_agari_synergy,
    -- pace_ntile2_weighted_avg_pos4_agari_synergy,
    -- pace_ntile2_weighted_place_rate,
    -- pace_ntile3_past_starts,
    -- pace_ntile3_past_places,
    -- pace_ntile3_past_pos4_agari_synergy,
    -- pace_ntile3_past_weighted_starts,
    -- pace_ntile3_past_weighted_places,
    -- pace_ntile3_past_weighted_pos4_agari_synergy,
    -- pace_ntile3_avg_pos4_agari_synergy,
    -- pace_ntile3_weighted_avg_pos4_agari_synergy,
    -- pace_ntile3_weighted_place_rate,
    -- pace_fast_minus_slow_place_rate,
    -- pace_fast_minus_slow_weighted_place_rate,
    -- past_weighted_starts,
    -- past_weighted_places,
    -- past_weighted_place_rate

  from {{ ref('feat_horse_past_metrics') }}
),

jockey_horse_pair_metrics as (
  select
    kettonum,
    jockey_cd,
    held_date,
    jockey_horse_pair_weighted_avg_pos4_agari_synergy,
    jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
    jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy
  from {{ ref('feat_jockey_horse_pair_metrics') }}
),

jockey_style as (
  select 
    jockey_cd,
    running_style_cd as running_style,
    relative_place_rate_3y as jockey_style_relative_place_rate_3y,
    relative_place_rate_3y_smooth as jockey_style_relative_place_rate_3y_smooth,
    jockey_style_base_diff_logit_smooth,
    jockey_style_avg_diff_logit_smooth,
    jockey_style_place_rate_3y,
    jockey_style_place_rate_3y_smooth,
    jockey_style_place_rate_3y_style_prior_smooth,
    held_year_month

  from {{ ref('feat_jockey_style') }}
),

trainer_stats as (
  select
    trainer_cd,
    held_year,
    trainer_place_rate_5y
  from {{ ref('feat_trainer_overall_hb') }}
),

workout_profile_metrics as (
  select
    race_id,
    kettonum,
    wood_4f1f_profile_place_rate_3y_smooth,
    hanro_4f1f_profile_place_rate_3y_smooth
  from {{ ref('feat_workout_profile_metrics') }}
),

workout_trainer_lap_time_1_metrics as (
  select
    race_id,
    kettonum,
    trainer_wood_lap_time_1_fast_excess_z_3y,
    trainer_hanro_lap_time_1_fast_excess_z_3y,
    trainer_week1_wood_lap_time_1_fast_excess_z_3y,
    trainer_week1_hanro_lap_time_1_fast_excess_z_3y
  from {{ ref('feat_workout_trainer_lap_time_1_metrics') }}
),

workout_trainer_haron_time_4_metrics as (
  select
    race_id,
    kettonum,
    trainer_wood_haron_time_4_fast_excess_z_3y,
    trainer_hanro_haron_time_4_fast_excess_z_3y,
    trainer_week1_wood_haron_time_4_fast_excess_z_3y,
    trainer_week1_hanro_haron_time_4_fast_excess_z_3y
  from {{ ref('feat_workout_trainer_haron_time_4_metrics') }}
),

trainer_old_stats as (
  select
    trainer_cd,
    old_cd,
    held_year,
    trainer_old_place_rate_5y
  from {{ ref('feat_trainer_age') }}
),

breeder_stats as (
  select
    breeder_cd,
    held_year,
    breeder_place_rate_5y,
    breeder_place_rate_5y_smooth,
    breeder_starts_5y
  from {{ ref('feat_breeder_overall') }}
),

odds as (
  select
    race_id,
    horse_number,
    odds_popularity,
    odds_tansho,
    j_odds_tansho
  from {{ ref('int_race_entry_odds') }}
),

metrics as (
  select
    race_id,
    kettonum,
    ten3f_vs_avg,
    ten3f_vs_avg_z,
    ten3f_avg_z,
    ten4f_vs_avg,
    pos4_z,
    pace_front_disadvantage,
    jockey_avg_place_rate,
    jockey_avg_place_rate_smooth,
    jockey_avg_place_rate_corrected,
    jockey_avg_place_rate_corrected_smooth,
    jockey_cluster_avg_place_rate_corrected,
    jockey_cluster_avg_place_rate_corrected_smooth,
    jockey_cluster_avg_diff_logit_smooth,
    jockey_surface_dist_pm200_place_rate_3y_smooth,
    jockey_surface_straight_distance_bucket_place_rate_3y_smooth,
    jockey_surface_straight_distance_bucket_avg_diff_logit_smooth,
    jockey_surface_turn_direction_place_rate_3y_smooth,
    jockey_surface_turn_direction_avg_diff_logit_smooth,
    jockey_turn_direction_place_rate_3y_smooth,
    jockey_turn_direction_avg_diff_logit_smooth,
    jockey_surface_jyo_place_rate_3y_smooth,
    jockey_surface_jyo_avg_diff_logit_smooth,
    jockey_starts_3y,
    jockey_places_3y
  from {{ ref('int_race_entry_metrics') }}
),

jockey_surface_style as (
  select
    jockey_cd,
    held_year_month,
    surface,
    running_style,
    jockey_surface_style_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_style') }}
),

course_running_style as (
  select
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    held_year,
    running_style_cd as running_style,
    course_style_place_rate_5y
  from {{ ref('feat_course_running_style') }}
),

course_sashi_ratio as (
  select
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    held_year,
    course_style_place_rate_5y as course_sashi_place_rate_5y
  from course_running_style
  where running_style = 3
),

jockey_pos4_bin as (
  select
    jockey_cd,
    held_year_month,
    pos4_bin5,
    jockey_pos4_bin5_starts_3y,
    jockey_pos4_bin5_place_rate_3y_smooth,
    jockey_pos4_bin5_relative_place_rate_3y_smooth
  from {{ ref('feat_jockey_pos4_bin') }}
),

cur_base as (
  select
    l.race_id,
    l.kettonum,
    l.popularity_ratio,
    l.horse_number,
    l.gate_number,
    l.surface,
    l.track_cd,
    l.surface_condition,
    l.surface_condition_cd,
    l.jyo_cd,
    l.distance_m,
    l.turn_direction,
    l.straight_distance_m,
    l.has_homestretch_slope,
    l.blinker_cd,
    coalesce(o.odds_popularity, l.popularity) as popularity,
    l.held_date,
    l.held_year,
    l.held_year_month,
    l.tenko_cd,
    l.jyuryo_cd,
    l.course_kubun_cd,
    l.race_level,
    l.old_cd,
    l.h_weight,
    l.weight_change,
    l.age,
    l.age_month,
    l.age_days,
    l.dm_rank,
    l.held_month,
    l.horse_number_ratio,
    l.kinryo,
    l.kinryo_adj,
    l.num_starters,
    m.jockey_avg_place_rate,
    m.jockey_avg_place_rate_smooth,
    m.jockey_avg_place_rate_corrected,
    m.jockey_avg_place_rate_corrected_smooth,
    m.jockey_cluster_avg_place_rate_corrected,
    m.jockey_cluster_avg_place_rate_corrected_smooth,
    m.jockey_cluster_avg_place_rate_corrected - m.jockey_avg_place_rate_corrected as jockey_cluster_avg_diff,
    m.jockey_cluster_avg_place_rate_corrected_smooth - m.jockey_avg_place_rate_corrected_smooth as jockey_cluster_avg_diff_smooth,
    m.jockey_cluster_avg_diff_logit_smooth,
    m.jockey_starts_3y,
    m.jockey_places_3y,
    m.jockey_surface_dist_pm200_place_rate_3y_smooth,
    m.jockey_surface_straight_distance_bucket_place_rate_3y_smooth,
    m.jockey_surface_straight_distance_bucket_avg_diff_logit_smooth,
    m.jockey_surface_turn_direction_place_rate_3y_smooth,
    m.jockey_surface_turn_direction_avg_diff_logit_smooth,
    m.jockey_turn_direction_place_rate_3y_smooth,
    m.jockey_turn_direction_avg_diff_logit_smooth,
    m.jockey_surface_jyo_place_rate_3y_smooth,
    m.jockey_surface_jyo_avg_diff_logit_smooth,
    jhpm.jockey_horse_pair_weighted_avg_pos4_agari_synergy,
    jhpm.jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
    jhpm.jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy,
    l.sex_cd,
    l.tozai_cd,
    l.sire_cat,
    l.sire_id,
    l.breeder_cd,
    l.trainer_cd,
    coalesce(o.odds_tansho, l.odds_tansho) as odds_tansho,
    coalesce(o.j_odds_tansho, o.odds_tansho, l.odds_tansho) as j_odds_tansho,
    case
      when coalesce(o.j_odds_tansho, o.odds_tansho, l.odds_tansho) > 0
        then ln(coalesce(o.j_odds_tansho, o.odds_tansho, l.odds_tansho))
      else null
    end as log_odds_tansho,
    l.course_cluster,
    l.ensei_type,
    l.jockey_cat,
    l.jockey_cd,
    m.ten3f_vs_avg,
    m.ten3f_vs_avg_z,
    m.ten3f_avg_z,
    m.ten4f_vs_avg,
    m.pos4_z,
    m.pace_front_disadvantage,
    l.wood_lap_time_1,
    l.wood_lap_time_2,
    l.wood_haron_time_4,
    l.wood_lap_time_1_z_tozai_day,
    l.wood_haron_time_4_z_tozai_day,
    l.wood_4f1f_profile_cat3,
    l.wood_tozai_cd,
    l.wood_late_sharpness,
    l.wood_haron_time_6,
    l.wood_haron_time_6_min,
    l.wood_lap_time_1_min,
    l.wood_accel_flag,
    l.week1_wood_lap_time_1,
    l.week1_wood_lap_time_2,
    l.week1_wood_haron_time_4,
    l.week1_wood_lap_time_1_z_tozai_day,
    l.week1_wood_haron_time_4_z_tozai_day,
    l.week1_wood_tozai_cd,
    l.week1_wood_late_sharpness,
    l.week1_wood_haron_time_6,
    l.week1_wood_haron_time_6_min,
    l.week1_wood_lap_time_1_min,
    l.week1_wood_accel_flag,
    l.hanro_lap_time_1,
    l.hanro_lap_time_2,
    l.hanro_haron_time_4,
    l.hanro_lap_time_1_z_tozai_day,
    l.hanro_haron_time_4_z_tozai_day,
    l.hanro_4f1f_profile_cat3,
    l.hanro_tozai_cd,
    l.hanro_late_sharpness,
    l.hanro_haron_time_4_min,
    l.hanro_lap_time_1_min,
    l.hanro_accel_flag,
    l.week1_hanro_lap_time_1,
    l.week1_hanro_lap_time_2,
    l.week1_hanro_haron_time_4,
    l.week1_hanro_lap_time_1_z_tozai_day,
    l.week1_hanro_haron_time_4_z_tozai_day,
    l.week1_hanro_tozai_cd,
    l.week1_hanro_late_sharpness,
    l.week1_hanro_haron_time_4_min,
    l.week1_hanro_lap_time_1_min,
    l.week1_hanro_accel_flag
  from (
    select * from {{ ref('int_race_entry_enriched') }}
  ) l
  left join metrics m
    on l.race_id = m.race_id
    and l.kettonum = m.kettonum
  left join odds o
    on l.race_id = o.race_id
    and l.horse_number = o.horse_number
  left join jockey_horse_pair_metrics jhpm
    on l.kettonum = jhpm.kettonum
    and l.jockey_cd = jhpm.jockey_cd
    and l.held_date = jhpm.held_date
  {% if is_incremental() %}
    where l.held_date >= current_date - interval '7 days'
  {% endif %}
),

joined_base as (
  select
    *
  from cur_base ha
  left join (
    select * from {{ ref('feat_course_profile') }}
  ) fc
    using (jyo_cd, distance_m, surface, gate_number, track_cd, held_year)
  left join (
    select * from {{ ref('feat_course_style_profile') }}
  ) fcs
    using (jyo_cd, distance_m, surface, track_cd, held_year)
  left join (
    select * from {{ ref('feat_race_relative_z') }}
  ) frz
    using (race_id, kettonum)
  left join horse_past_metrics hpm
    using (kettonum, held_date)
  left join sire_metrics sm
    using (race_id, kettonum)
  left join dam_metrics dm
    using (race_id, kettonum)
  left join damsire_metrics dsm
    using (race_id, kettonum)
  left join workout_profile_metrics wpm
    using (race_id, kettonum)
  left join workout_trainer_lap_time_1_metrics wtlm
    using (race_id, kettonum)
  left join workout_trainer_haron_time_4_metrics wthm
    using (race_id, kettonum)
  left join jockey_style js
    using (jockey_cd, held_year_month, running_style)
  left join jockey_surface_style jss
    using (jockey_cd, held_year_month, surface, running_style)
  left join trainer_stats ts
    using (trainer_cd, held_year)
  left join trainer_old_stats tos
    using (trainer_cd, old_cd, held_year)
  left join breeder_stats bs
    using (breeder_cd, held_year)
  left join course_running_style crs
    using (jyo_cd, distance_m, surface, track_cd, held_year, running_style)
  left join course_sashi_ratio csr
    using (jyo_cd, distance_m, surface, track_cd, held_year)
  {% if is_incremental() %}
    where ha.held_date >= current_date - interval '7 days'
  {% endif %}
),

te_inputs as (
  select
    jb.*,
    least(
      greatest(
        coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3),
        0
      ),
      1
    ) as pred_pos4_for_jockey_te,
    case
      when coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3) is null then null
      when least(greatest(coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3), 0), 1) < 0.2 then 1
      when least(greatest(coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3), 0), 1) < 0.4 then 2
      when least(greatest(coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3), 0), 1) < 0.6 then 3
      when least(greatest(coalesce(jb.horse_corner4_wavg5_recent, jb.horse_corner4_avg5, jb.horse_corner4_avg3), 0), 1) < 0.8 then 4
      else 5
    end as pred_pos4_bin5_hard,
    least(
      greatest(jb.running_style_avg3, 1),
      4
    ) as pred_running_style_for_jockey_te
  from joined_base jb
)

select
  tr.*,
  jpbh.jockey_pos4_bin5_starts_3y as jockey_pos4_bin5_starts_3y_hard,
  jpbh.jockey_pos4_bin5_place_rate_3y_smooth as jockey_pos4_bin5_place_rate_3y_smooth_hard,
  jpbh.jockey_pos4_bin5_relative_place_rate_3y_smooth as jockey_pos4_bin5_relative_place_rate_3y_smooth_hard,
  case
    when tr.pred_pos4_for_jockey_te is null then null
    else
      (w.weight1 * coalesce(jpbs1.jockey_pos4_bin5_starts_3y, 0))
      + (w.weight2 * coalesce(jpbs2.jockey_pos4_bin5_starts_3y, 0))
      + (w.weight3 * coalesce(jpbs3.jockey_pos4_bin5_starts_3y, 0))
      + (w.weight4 * coalesce(jpbs4.jockey_pos4_bin5_starts_3y, 0))
      + (w.weight5 * coalesce(jpbs5.jockey_pos4_bin5_starts_3y, 0))
  end as jockey_pos4_bin5_starts_3y_soft,
  case
    when tr.pred_pos4_for_jockey_te is null then null
    else
      (
        (case when jpbs1.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight1 * jpbs1.jockey_pos4_bin5_place_rate_3y_smooth end) +
        (case when jpbs2.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight2 * jpbs2.jockey_pos4_bin5_place_rate_3y_smooth end) +
        (case when jpbs3.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight3 * jpbs3.jockey_pos4_bin5_place_rate_3y_smooth end) +
        (case when jpbs4.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight4 * jpbs4.jockey_pos4_bin5_place_rate_3y_smooth end) +
        (case when jpbs5.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight5 * jpbs5.jockey_pos4_bin5_place_rate_3y_smooth end)
      ) / nullif(
        (case when jpbs1.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight1 end) +
        (case when jpbs2.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight2 end) +
        (case when jpbs3.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight3 end) +
        (case when jpbs4.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight4 end) +
        (case when jpbs5.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight5 end),
        0
      )
  end as jockey_pos4_bin5_place_rate_3y_smooth_soft,
  case
    when tr.pred_pos4_for_jockey_te is null then null
    else
      (
        (case when jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight1 * jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth end) +
        (case when jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight2 * jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth end) +
        (case when jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight3 * jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth end) +
        (case when jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight4 * jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth end) +
        (case when jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight5 * jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
      ) / nullif(
        (case when jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight1 end) +
        (case when jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight2 end) +
        (case when jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight3 end) +
        (case when jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight4 end) +
        (case when jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight5 end),
        0
      )
  end as jockey_pos4_bin5_relative_place_rate_3y_smooth_soft,
  case
    when tr.pred_running_style_for_jockey_te is null then null
    else
      (
        (case when jssoft1.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight1 * jssoft1.jockey_style_place_rate_3y_smooth end) +
        (case when jssoft2.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight2 * jssoft2.jockey_style_place_rate_3y_smooth end) +
        (case when jssoft3.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight3 * jssoft3.jockey_style_place_rate_3y_smooth end) +
        (case when jssoft4.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight4 * jssoft4.jockey_style_place_rate_3y_smooth end)
      ) / nullif(
        (case when jssoft1.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight1 end) +
        (case when jssoft2.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight2 end) +
        (case when jssoft3.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight3 end) +
        (case when jssoft4.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight4 end),
        0
      )
  end as jockey_style_place_rate_3y_smooth_soft
from te_inputs tr
left join jockey_pos4_bin jpbh
  on tr.jockey_cd = jpbh.jockey_cd
  and tr.held_year_month = jpbh.held_year_month
  and tr.pred_pos4_bin5_hard = jpbh.pos4_bin5
left join jockey_pos4_bin jpbs1
  on tr.jockey_cd = jpbs1.jockey_cd
  and tr.held_year_month = jpbs1.held_year_month
  and jpbs1.pos4_bin5 = 1
left join jockey_pos4_bin jpbs2
  on tr.jockey_cd = jpbs2.jockey_cd
  and tr.held_year_month = jpbs2.held_year_month
  and jpbs2.pos4_bin5 = 2
left join jockey_pos4_bin jpbs3
  on tr.jockey_cd = jpbs3.jockey_cd
  and tr.held_year_month = jpbs3.held_year_month
  and jpbs3.pos4_bin5 = 3
left join jockey_pos4_bin jpbs4
  on tr.jockey_cd = jpbs4.jockey_cd
  and tr.held_year_month = jpbs4.held_year_month
  and jpbs4.pos4_bin5 = 4
left join jockey_pos4_bin jpbs5
  on tr.jockey_cd = jpbs5.jockey_cd
  and tr.held_year_month = jpbs5.held_year_month
  and jpbs5.pos4_bin5 = 5
left join jockey_style jssoft1
  on tr.jockey_cd = jssoft1.jockey_cd
  and tr.held_year_month = jssoft1.held_year_month
  and jssoft1.running_style = 1
left join jockey_style jssoft2
  on tr.jockey_cd = jssoft2.jockey_cd
  and tr.held_year_month = jssoft2.held_year_month
  and jssoft2.running_style = 2
left join jockey_style jssoft3
  on tr.jockey_cd = jssoft3.jockey_cd
  and tr.held_year_month = jssoft3.held_year_month
  and jssoft3.running_style = 3
left join jockey_style jssoft4
  on tr.jockey_cd = jssoft4.jockey_cd
  and tr.held_year_month = jssoft4.held_year_month
  and jssoft4.running_style = 4
cross join lateral (
  select
    case when tr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(tr.pred_pos4_for_jockey_te - 0.1) / 0.2, 0) end as raw_weight1,
    case when tr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(tr.pred_pos4_for_jockey_te - 0.3) / 0.2, 0) end as raw_weight2,
    case when tr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(tr.pred_pos4_for_jockey_te - 0.5) / 0.2, 0) end as raw_weight3,
    case when tr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(tr.pred_pos4_for_jockey_te - 0.7) / 0.2, 0) end as raw_weight4,
    case when tr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(tr.pred_pos4_for_jockey_te - 0.9) / 0.2, 0) end as raw_weight5
) wr
cross join lateral (
  select
    case
      when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null
      else wr.raw_weight1 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0))
    end as weight1,
    case
      when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null
      else wr.raw_weight2 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0))
    end as weight2,
    case
      when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null
      else wr.raw_weight3 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0))
    end as weight3,
    case
      when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null
      else wr.raw_weight4 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0))
    end as weight4,
    case
      when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null
      else wr.raw_weight5 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0))
    end as weight5
) w
cross join lateral (
  select
    case when tr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(tr.pred_running_style_for_jockey_te - 1.0), 0) end as raw_weight1,
    case when tr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(tr.pred_running_style_for_jockey_te - 2.0), 0) end as raw_weight2,
    case when tr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(tr.pred_running_style_for_jockey_te - 3.0), 0) end as raw_weight3,
    case when tr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(tr.pred_running_style_for_jockey_te - 4.0), 0) end as raw_weight4
) swr
cross join lateral (
  select
    case
      when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null
      else swr.raw_weight1 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0))
    end as weight1,
    case
      when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null
      else swr.raw_weight2 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0))
    end as weight2,
    case
      when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null
      else swr.raw_weight3 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0))
    end as weight3,
    case
      when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null
      else swr.raw_weight4 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0))
    end as weight4
) sw
