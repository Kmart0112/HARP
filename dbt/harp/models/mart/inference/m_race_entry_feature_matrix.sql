{% set feature_input_mode = var('feature_input_mode', var('feature_snapshot_mode', 'training')) %}

{% if feature_input_mode not in ['training', 'latest', 'all'] %}
  {{ exceptions.raise_compiler_error("feature_input_mode must be one of: training, latest, all") }}
{% endif %}

{% set include_live_context = feature_input_mode in ['latest', 'all'] %}
{% set include_training_context = feature_input_mode in ['training', 'all'] %}
{% set is_live_context = feature_input_mode == 'latest' %}

{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['feature_matrix', 'race_day_live', 'training'],
  indexes=[
    {'columns': ['race_id', 'kettonum'], 'unique': True},
    {'columns': ['held_date']}
  ]
) }}

-- depends_on: {{ ref('int_race_day_feature_context') }}
-- depends_on: {{ ref('int_race_entry_feature_context') }}

with context as (
  {% if include_live_context %}
  select *
  from {{ ref('int_race_day_feature_context') }}
  where held_date = {{ target_held_date_expr() }}
  {% endif %}
  {% if include_live_context and include_training_context %}
  union all
  {% endif %}
  {% if include_training_context %}
  select *
  from {{ ref('int_race_entry_feature_context') }}
  where 1 = 1
  {% if var('target_held_date', none) is not none %}
    and held_date = '{{ var("target_held_date") }}'::date
  {% elif var('race_from_date', none) is not none or var('race_to_date', none) is not none %}
    {% if var('race_from_date', none) is not none %}
      and held_date >= '{{ var("race_from_date") }}'::date
    {% endif %}
    {% if var('race_to_date', none) is not none %}
      and held_date <= '{{ var("race_to_date") }}'::date
    {% endif %}
  {% elif is_incremental() %}
    and held_date >= current_date - interval '7 days'
  {% endif %}
  {% if include_live_context %}
    and held_date <> {{ target_held_date_expr() }}
  {% endif %}
  {% endif %}
),

trainer_stats as (
  select
    trainer_cd,
    held_year,
    trainer_starts_5y,
    trainer_places_5y,
    trainer_place_rate_5y
  from {{ ref('feat_trainer_overall_hb') }} ts_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.trainer_cd = ts_src.trainer_cd
      and c.held_year = ts_src.held_year
  )
  {% endif %}
),

trainer_old_stats as (
  select
    trainer_cd,
    old_cd,
    held_year,
    trainer_old_starts_5y,
    trainer_old_places_5y,
    trainer_old_place_rate_5y
  from {{ ref('feat_trainer_age') }} tos_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.trainer_cd = tos_src.trainer_cd
      and c.old_cd = tos_src.old_cd
      and c.held_year = tos_src.held_year
  )
  {% endif %}
),

breeder_stats as (
  select
    breeder_cd,
    held_year,
    breeder_starts_5y,
    breeder_places_5y,
    breeder_wins_5y,
    breeder_place_rate_5y,
    breeder_place_rate_5y_smooth
  from {{ ref('feat_breeder_overall') }} bs_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.breeder_cd = bs_src.breeder_cd
      and c.held_year = bs_src.held_year
  )
  {% endif %}
),

entry_pre_race as (
  select
    race_id,
    kettonum,
    dm_rank,
    wood_lap_time_1,
    wood_lap_time_2,
    wood_haron_time_4,
    wood_lap_time_1_z_tozai_day,
    wood_haron_time_4_z_tozai_day,
    wood_4f1f_profile_cat3,
    wood_tozai_cd,
    wood_late_sharpness,
    wood_haron_time_6,
    wood_haron_time_6_min,
    wood_lap_time_1_min,
    wood_accel_flag,
    week1_wood_lap_time_1,
    week1_wood_lap_time_2,
    week1_wood_haron_time_4,
    week1_wood_lap_time_1_z_tozai_day,
    week1_wood_haron_time_4_z_tozai_day,
    week1_wood_tozai_cd,
    week1_wood_late_sharpness,
    week1_wood_haron_time_6,
    week1_wood_haron_time_6_min,
    week1_wood_lap_time_1_min,
    week1_wood_accel_flag,
    hanro_lap_time_1,
    hanro_lap_time_2,
    hanro_haron_time_4,
    hanro_lap_time_1_z_tozai_day,
    hanro_haron_time_4_z_tozai_day,
    hanro_4f1f_profile_cat3,
    hanro_tozai_cd,
    hanro_late_sharpness,
    hanro_haron_time_4_min,
    hanro_lap_time_1_min,
    hanro_accel_flag,
    week1_hanro_lap_time_1,
    week1_hanro_lap_time_2,
    week1_hanro_haron_time_4,
    week1_hanro_lap_time_1_z_tozai_day,
    week1_hanro_haron_time_4_z_tozai_day,
    week1_hanro_tozai_cd,
    week1_hanro_late_sharpness,
    week1_hanro_haron_time_4_min,
    week1_hanro_lap_time_1_min,
    week1_hanro_accel_flag
  from {{ ref('int_race_entry_enriched') }} epr_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.race_id = epr_src.race_id
      and c.kettonum = epr_src.kettonum
  )
  {% endif %}
),

horse_past_metrics as (
  select
    kettonum,
    held_date,
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
  from {{ ref('feat_horse_past_metrics') }} hpm_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.kettonum = hpm_src.kettonum
      and c.held_date = hpm_src.held_date
  )
  {% endif %}
),

jockey_horse_pair_metrics as (
  select
    kettonum,
    jockey_cd,
    held_date,
    jockey_horse_pair_weighted_avg_pos4_agari_synergy,
    jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
    jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy
  from {{ ref('feat_jockey_horse_pair_metrics') }} jhpm_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.kettonum = jhpm_src.kettonum
      and c.jockey_cd = jhpm_src.jockey_cd
      and c.held_date = jhpm_src.held_date
  )
  {% endif %}
),

workout_profile_metrics as (
  select
    race_id,
    kettonum,
    wood_4f1f_profile_place_rate_3y_smooth,
    hanro_4f1f_profile_place_rate_3y_smooth
  from {{ ref('feat_workout_profile_metrics') }} wpm_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.race_id = wpm_src.race_id
      and c.kettonum = wpm_src.kettonum
  )
  {% endif %}
),

workout_trainer_lap_time_1_metrics as (
  select
    race_id,
    kettonum,
    trainer_wood_lap_time_1_fast_excess_z_3y,
    trainer_hanro_lap_time_1_fast_excess_z_3y,
    trainer_week1_wood_lap_time_1_fast_excess_z_3y,
    trainer_week1_hanro_lap_time_1_fast_excess_z_3y
  from {{ ref('feat_workout_trainer_lap_time_1_metrics') }} wtlm_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.race_id = wtlm_src.race_id
      and c.kettonum = wtlm_src.kettonum
  )
  {% endif %}
),

workout_trainer_haron_time_4_metrics as (
  select
    race_id,
    kettonum,
    trainer_wood_haron_time_4_fast_excess_z_3y,
    trainer_hanro_haron_time_4_fast_excess_z_3y,
    trainer_week1_wood_haron_time_4_fast_excess_z_3y,
    trainer_week1_hanro_haron_time_4_fast_excess_z_3y
  from {{ ref('feat_workout_trainer_haron_time_4_metrics') }} wthm_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.race_id = wthm_src.race_id
      and c.kettonum = wthm_src.kettonum
  )
  {% endif %}
),

course_style_profile as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    top3_corner3_pos_avg_5y,
    top3_corner3_pos_var_5y
  from {{ ref('feat_course_style_profile') }} csp_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.held_year = csp_src.held_year
      and c.jyo_cd = csp_src.jyo_cd
      and c.distance_m = csp_src.distance_m
      and c.surface = csp_src.surface
      and c.track_cd = csp_src.track_cd
  )
  {% endif %}
),

course_profile as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    gate_number,
    cum_starts_5y,
    diff_gate_pp_5y,
    diff_gate_pp_std_5y,
    p_place_5y
  from {{ ref('feat_course_profile') }} cp_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.held_year = cp_src.held_year
      and c.jyo_cd = cp_src.jyo_cd
      and c.distance_m = cp_src.distance_m
      and c.surface = cp_src.surface
      and c.track_cd = cp_src.track_cd
      and c.gate_number = cp_src.gate_number
  )
  {% endif %}
),

course_sashi_ratio as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    course_style_place_rate_5y as course_sashi_place_rate_5y
  from {{ ref('feat_course_running_style') }} csr_src
  where running_style_cd = 3
  {% if is_live_context %}
    and exists (
      select 1
      from context c
      where c.held_year = csr_src.held_year
        and c.jyo_cd = csr_src.jyo_cd
        and c.distance_m = csr_src.distance_m
        and c.surface = csr_src.surface
        and c.track_cd = csr_src.track_cd
    )
  {% endif %}
),

course_running_style as (
  select
    held_year,
    jyo_cd,
    distance_m,
    surface,
    track_cd,
    running_style_cd as running_style,
    course_style_place_rate_5y
  from {{ ref('feat_course_running_style') }} crs_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.held_year = crs_src.held_year
      and c.jyo_cd = crs_src.jyo_cd
      and c.distance_m = crs_src.distance_m
      and c.surface = crs_src.surface
      and c.track_cd = crs_src.track_cd
  )
  {% endif %}
),

race_relative_features as (
  select
    race_id,
    kettonum,
    is_shokyu,
    race_level_diff,
    p1_race_level,
    is_jockey_change,
    distance_change,
    p1_distance_m,
    is_surface_changed,
    course_cluster_change,
    race_interval_days,
    p2_race_interval_days,
    horse_corner4_sd5,
    horse_corner4_trend5,
    pos4_agari_synergy_sd,
    horse_rel_agari3f_avg3,
    agari3f_rank_avg3,
    agari3f_rank_percentile_avg3,
    horse_rel_agari3f_avg5,
    horse_rel_agari3f_wavg5_recent,
    pos4_agari_synergy_avg3,
    pos4_agari_synergy_avg5,
    pos4_agari_synergy_wavg5_recent,
    pos4_agari_synergy_sd5,
    pos4_agari_synergy_trend5,
    p1_pos4_agari_synergy,
    p2_pos4_agari_synergy,
    p3_pos4_agari_synergy,
    p1_time_diff,
    p2_time_diff,
    p3_time_diff,
    p1_ten3f_vs_avg,
    p2_ten3f_vs_avg,
    p3_ten3f_vs_avg,
    ten3f_vs_avg_avg3,
    p1_pace_front_disadvantage,
    p2_pace_front_disadvantage,
    p3_pace_front_disadvantage,
    pace_front_disadvantage_avg3,
    p1_time_vs_pace_avg,
    p2_time_vs_pace_avg,
    p3_time_vs_pace_avg,
    time_diff_avg3,
    time_diff_avg5,
    time_diff_wavg5_recent,
    time_diff_sd5,
    time_diff_trend5,
    time_vs_pace_avg_avg3,
    time_vs_pace_avg_avg5,
    time_vs_pace_avg_wavg5_recent,
    time_vs_avg_avg5,
    time_vs_avg_wavg5_recent,
    time_vs_avg_sd5,
    time_vs_avg_trend5,
    time_vs_avg_adjusted_avg5,
    time_vs_avg_adjusted_wavg5_recent,
    time_diff_adjusted_avg5,
    time_vs_avg_sd,
    p1_corner4,
    p2_corner4,
    p3_corner4,
    horse_corner4_sd3,
    horse_kinryo_avg3,
    pos4_agari_synergy_slope3,
    pos4_agari_synergy_trend3_voladj,
    pos4_agari_synergy_short_long_gap,
    same_cluster_avg_pos4_agari_synergy_avg3,
    same_cluster_pos4_agari_synergy_diff,
    p1_wood_lap_time_1,
    p1_wood_lap_time_1_z_tozai_day,
    p1_trainer_wood_lap_time_1_fast_excess_z_3y,
    p1_hanro_lap_time_1,
    p1_hanro_lap_time_1_z_tozai_day,
    p1_trainer_hanro_lap_time_1_fast_excess_z_3y,
    jockey_avg_place_rate_avg3,
    jockey_avg_place_rate_avg3_smooth,
    p1_weight,
    p1_weight_change,
    weight_change_ratio,
    condition_change_score,
    distance_change_score,
    surface_change_score,
    jockey_place_rate_diff_ratio,
    jockey_place_rate_diff_ratio_smooth,
    num_past3_races,
    num_past5_races,
    course_cluster_change_score,
    p1_course_cluster,
    p1_jyo_cd,
    blinker_added,
    num_front_runners,
    pace_front_runners_avg,
    pace_front_runners_min,
    rel_agari_z,
    corner4_rate_z,
    corner4_rate_avg5_z,
    corner4_trend5_z,
    race_avg_corner4,
    race_stddev_corner4,
    race_styele_score,
    horse_styele_diff,
    style_score,
    time_vs_avg_z,
    time_vs_avg_avg5_z,
    time_vs_avg_wavg5_recent_z,
    time_vs_avg_wavg5_recent_diff_top_in_race,
    time_vs_avg_sd5_z,
    time_vs_avg_trend5_z,
    time_vs_pace_avg_z,
    time_vs_pace_avg_avg5_z,
    time_vs_pace_avg_wavg5_recent_z,
    time_vs_avg_diff_top_in_race,
    time_vs_avg_adjusted_z,
    time_vs_avg_adjusted_avg5_z,
    time_vs_avg_adjusted_wavg5_recent_z,
    time_vs_avg_adjusted_wavg5_recent_diff_top_in_race,
    time_vs_avg_adjusted_diff_top_in_race,
    time_diff_z,
    time_diff_robust,
    time_diff_avg5_z,
    time_diff_wavg5_recent_z,
    time_diff_wavg5_recent_robust,
    time_diff_wavg5_recent_diff_top_in_race,
    time_diff_wavg5_recent_rank,
    time_diff_sd5_z,
    time_diff_trend5_z,
    time_diff_rank,
    pos4_agari_synergy_z,
    pos4_agari_synergy_avg5_z,
    pos4_agari_synergy_wavg5_recent_z,
    race_pos4_agari_synergy_wavg5_recent_median,
    race_pos4_agari_synergy_wavg5_recent_iqr,
    pos4_agari_synergy_wavg5_recent_robust,
    pos4_agari_synergy_wavg5_recent_diff_top_in_race,
    pos4_agari_synergy_sd5_z,
    pos4_agari_synergy_trend5_z,
    pos4_agari_synergy_diff_top_in_race,
    pos4_agari_synergy_max_z,
    agari_good_z,
    rel_agari_min_z,
    same_cluster_avg_pos4_agari_synergy_z,
    same_turn_direction_surface_avg_pos4_agari_synergy_z,
    same_homestretch_slope_surface_avg_pos4_agari_synergy_z,
    same_distance_weighted_avg_pos4_agari_synergy_z,
    same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_z,
    same_cluster_avg_pos4_agari_synergy_rank,
    time_vs_avg_min_z,
    time_diff_adjusted_z,
    time_diff_adjusted_avg5_z,
    past_same_cluster_avg_pos4_as_z,
    age_days_z,
    kinryo_z,
    kinryo_adj_z,
    jockey_place_rate_z,
    jockey_place_rate_z_smooth,
    jockey_place_rate_3y_logit_z,
    jockey_place_rate_3y_logit_z_smooth,
    jockey_cluster_avg_place_rate_corrected_logit_z,
    jockey_cluster_avg_place_rate_corrected_rank,
    race_avg_jockey_place_rate,
    race_avg_jockey_place_rate_smooth,
    horse_corner4_avg3,
    horse_corner4_avg5,
    horse_corner4_wavg5_recent,
    running_style_avg3,
    running_style
  from {{ ref('feat_race_relative_z') }} rrf_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.race_id = rrf_src.race_id
      and c.kettonum = rrf_src.kettonum
  )
  {% endif %}
),

jockey_style as (
  select
    jockey_cd,
    held_year_month,
    running_style_cd as running_style,
    relative_place_rate_3y as jockey_style_relative_place_rate_3y,
    relative_place_rate_3y_smooth as jockey_style_relative_place_rate_3y_smooth,
    jockey_style_base_diff_logit_smooth,
    jockey_style_avg_diff_logit_smooth,
    jockey_style_place_rate_3y,
    jockey_style_place_rate_3y_smooth,
    jockey_style_place_rate_3y_style_prior_smooth
  from {{ ref('feat_jockey_style') }} js_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = js_src.jockey_cd
      and c.held_year_month = js_src.held_year_month
  )
  {% endif %}
),

jockey_surface_style as (
  select
    jockey_cd,
    held_year_month,
    surface,
    running_style,
    jockey_surface_style_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_style') }} jss_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jss_src.jockey_cd
      and c.held_year_month = jss_src.held_year_month
      and c.surface = jss_src.surface
  )
  {% endif %}
),

jockey_pos4_bin as (
  select
    jockey_cd,
    held_year_month,
    pos4_bin5,
    jockey_pos4_bin5_starts_3y,
    jockey_pos4_bin5_place_rate_3y_smooth,
    jockey_pos4_bin5_relative_place_rate_3y_smooth
  from {{ ref('feat_jockey_pos4_bin') }} jpb_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jpb_src.jockey_cd
      and c.held_year_month = jpb_src.held_year_month
  )
  {% endif %}
),

jockey_overall as (
  select
    jockey_cd,
    held_year_month,
    jockey_starts_3y,
    jockey_places_3y,
    jockey_wins_3y,
    jockey_place_rate_3y,
    jockey_place_rate_3y_smooth,
    jockey_place_rate_3y_logit,
    jockey_place_rate_3y_logit_smooth
  from {{ ref('feat_jockey_yearly_overall') }} jo_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jo_src.jockey_cd
      and c.held_year_month = jo_src.held_year_month
  )
  {% endif %}
),

jockey_cluster as (
  select
    jockey_cd,
    held_year_month,
    course_cluster,
    jockey_cluster_starts_3y,
    jockey_cluster_places_3y,
    jockey_cluster_place_rate_3y,
    jockey_cluster_place_rate_3y_smooth,
    jockey_cluster_avg_diff_logit_smooth
  from {{ ref('feat_jockey_yearly_cluster') }} jc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jc_src.jockey_cd
      and c.held_year_month = jc_src.held_year_month
      and c.course_cluster = jc_src.course_cluster
  )
  {% endif %}
),

jockey_surface_distance as (
  select
    jockey_cd,
    held_year_month,
    surface,
    distance_m,
    jockey_surface_distance_starts_3y,
    jockey_surface_distance_places_3y,
    jockey_surface_distance_place_rate_3y,
    jockey_surface_distance_place_rate_3y_smooth,
    jockey_surface_dist_pm200_starts_3y,
    jockey_surface_dist_pm200_places_3y,
    jockey_surface_dist_pm200_place_rate_3y,
    jockey_surface_dist_pm200_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_distance') }} jsd_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jsd_src.jockey_cd
      and c.held_year_month = jsd_src.held_year_month
      and c.surface = jsd_src.surface
      and c.distance_m = jsd_src.distance_m
  )
  {% endif %}
),

jockey_surface_jyo as (
  select
    jockey_cd,
    held_year_month,
    surface,
    jyo_cd,
    jockey_surface_jyo_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_jyo') }} jsj_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jsj_src.jockey_cd
      and c.held_year_month = jsj_src.held_year_month
      and c.surface = jsj_src.surface
      and c.jyo_cd = jsj_src.jyo_cd
  )
  {% endif %}
),

jockey_surface_straight_distance_bucket as (
  select
    jockey_cd,
    held_year_month,
    surface,
    straight_distance_bucket,
    jockey_surface_straight_distance_bucket_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_straight_distance_bucket') }} jssdb_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jssdb_src.jockey_cd
      and c.held_year_month = jssdb_src.held_year_month
      and c.surface = jssdb_src.surface
      and c.straight_distance_bucket = jssdb_src.straight_distance_bucket
  )
  {% endif %}
),

jockey_surface_turn_direction as (
  select
    jockey_cd,
    held_year_month,
    surface,
    turn_direction,
    jockey_surface_turn_direction_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_surface_turn_direction') }} jstd_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jstd_src.jockey_cd
      and c.held_year_month = jstd_src.held_year_month
      and c.surface = jstd_src.surface
      and c.turn_direction = jstd_src.turn_direction
  )
  {% endif %}
),

jockey_turn_direction as (
  select
    jockey_cd,
    held_year_month,
    turn_direction,
    jockey_turn_direction_place_rate_3y_smooth
  from {{ ref('feat_jockey_yearly_turn_direction') }} jtd_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.jockey_cd = jtd_src.jockey_cd
      and c.held_year_month = jtd_src.held_year_month
      and c.turn_direction = jtd_src.turn_direction
  )
  {% endif %}
),

sire_overall as (
  select
    sire_id,
    held_year_month,
    sire_starts_5y,
    sire_places_5y,
    sire_avg_place_rate,
    sire_avg_place_rate_smooth,
    sire_avg_pos4_agari_synergy,
    sire_avg_time_diff,
    sire_career_months,
    sire_is_early_phase_3y
  from {{ ref('feat_sire_yearly_overall') }} so_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = so_src.sire_id
      and c.held_year_month = so_src.held_year_month
  )
  {% endif %}
),

sire_cluster as (
  select
    sire_id,
    held_year_month,
    course_cluster,
    same_cluster_sire_starts_5y,
    same_cluster_sire_places_5y,
    same_cluster_sire_wins_5y,
    same_cluster_sire_time_diffs_5y,
    same_cluster_sire_avg_pos4_agari_synergy
  from {{ ref('feat_sire_yearly_cluster') }} sc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = sc_src.sire_id
      and c.held_year_month = sc_src.held_year_month
      and c.course_cluster = sc_src.course_cluster
  )
  {% endif %}
),

sire_age as (
  select
    sire_id,
    held_year_month,
    age,
    same_age_sire_starts_5y,
    same_age_sire_places_5y,
    age_place_rate_3y_prior,
    same_age_sire_avg_pos4_agari_synergy,
    same_age_sire_avg_place_rate_smooth_prev_age
  from {{ ref('feat_sire_yearly_age') }} sa_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = sa_src.sire_id
      and c.held_year_month = sa_src.held_year_month
      and (case when c.age >= 8 then 8 else c.age end) = sa_src.age
  )
  {% endif %}
),

sire_old_cd as (
  select
    sire_id,
    held_year_month,
    old_cd,
    same_old_cd_sire_starts_5y,
    same_old_cd_sire_places_5y,
    same_old_cd_sire_avg_pos4_agari_synergy,
    same_old_cd_sire_avg_place_rate_smooth_prev_old_cd
  from {{ ref('feat_sire_yearly_old_cd') }} soc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = soc_src.sire_id
      and c.held_year_month = soc_src.held_year_month
      and c.old_cd = soc_src.old_cd
  )
  {% endif %}
),

sire_sex_cd as (
  select
    sire_id,
    held_year_month,
    sex_cd,
    same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd,
    same_sex_cd_sire_avg_pos4_agari_synergy
  from {{ ref('feat_sire_yearly_sex_cd') }} ssc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = ssc_src.sire_id
      and c.held_year_month = ssc_src.held_year_month
      and c.sex_cd = ssc_src.sex_cd
  )
  {% endif %}
),

sire_weight as (
  select
    sire_id,
    held_year_month,
    h_weight_bin,
    same_weight_sire_starts_5y,
    same_weight_sire_places_5y,
    same_weight_sire_place_rate_5y
  from {{ ref('feat_sire_weight') }} sw_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = sw_src.sire_id
      and c.held_year_month = sw_src.held_year_month
      and c.h_weight_bin = sw_src.h_weight_bin
  )
  {% endif %}
),

sire_surface_distance_pm200 as (
  select
    sire_id,
    held_year_month,
    surface,
    distance_m,
    same_surface_dist_pm200_sire_starts_5y,
    same_surface_dist_pm200_sire_places_5y,
    same_surface_dist_pm200_sire_place_rate_5y,
    same_surface_dist_pm200_sire_avg_pos4_agari_synergy
  from {{ ref('feat_sire_yearly_surface_distance_pm200') }} sdp_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.sire_id = sdp_src.sire_id
      and c.held_year_month = sdp_src.held_year_month
      and c.surface = sdp_src.surface
      and c.distance_m = sdp_src.distance_m
  )
  {% endif %}
),

dam_overall as (
  select
    dam_id,
    held_year_month,
    dam_starts_5y,
    dam_avg_place_rate,
    dam_avg_place_rate_smooth,
    dam_avg_pos4_agari_synergy,
    dam_avg_time_diff
  from {{ ref('feat_dam_yearly_overall') }} dy_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.dam_id = dy_src.dam_id
      and c.held_year_month = dy_src.held_year_month
  )
  {% endif %}
),

dam_cluster as (
  select
    dam_id,
    held_year_month,
    course_cluster,
    same_cluster_dam_starts_5y,
    same_cluster_dam_avg_place_rate,
    same_cluster_dam_avg_place_rate_smooth,
    same_cluster_dam_avg_pos4_agari_synergy
  from {{ ref('feat_dam_yearly_cluster') }} dc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.dam_id = dc_src.dam_id
      and c.held_year_month = dc_src.held_year_month
      and c.course_cluster = dc_src.course_cluster
  )
  {% endif %}
),

damsire_overall as (
  select
    damsire_id,
    held_year_month,
    damsire_starts_5y,
    damsire_avg_place_rate,
    damsire_avg_place_rate_smooth,
    damsire_avg_pos4_agari_synergy,
    damsire_avg_time_diff
  from {{ ref('feat_damsire_yearly_overall') }} dsy_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.damsire_id = dsy_src.damsire_id
      and c.held_year_month = dsy_src.held_year_month
  )
  {% endif %}
),

damsire_cluster as (
  select
    damsire_id,
    held_year_month,
    course_cluster,
    same_cluster_damsire_starts_5y,
    same_cluster_damsire_avg_place_rate,
    same_cluster_damsire_avg_place_rate_smooth,
    same_cluster_damsire_avg_pos4_agari_synergy
  from {{ ref('feat_damsire_yearly_cluster') }} dsc_src
  {% if is_live_context %}
  where exists (
    select 1
    from context c
    where c.damsire_id = dsc_src.damsire_id
      and c.held_year_month = dsc_src.held_year_month
      and c.course_cluster = dsc_src.course_cluster
  )
  {% endif %}
),

feature_rows as (
  select
    c.*,
    ts.trainer_starts_5y,
    ts.trainer_places_5y,
    ts.trainer_place_rate_5y,
    tos.trainer_old_starts_5y,
    tos.trainer_old_places_5y,
    tos.trainer_old_place_rate_5y,
    bs.breeder_starts_5y,
    bs.breeder_places_5y,
    bs.breeder_wins_5y,
    bs.breeder_place_rate_5y,
    bs.breeder_place_rate_5y_smooth,
    epr.dm_rank,
    epr.wood_lap_time_1,
    epr.wood_lap_time_2,
    epr.wood_haron_time_4,
    epr.wood_lap_time_1_z_tozai_day,
    epr.wood_haron_time_4_z_tozai_day,
    epr.wood_4f1f_profile_cat3,
    epr.wood_tozai_cd,
    epr.wood_late_sharpness,
    epr.wood_haron_time_6,
    epr.wood_haron_time_6_min,
    epr.wood_lap_time_1_min,
    epr.wood_accel_flag,
    epr.week1_wood_lap_time_1,
    epr.week1_wood_lap_time_2,
    epr.week1_wood_haron_time_4,
    epr.week1_wood_lap_time_1_z_tozai_day,
    epr.week1_wood_haron_time_4_z_tozai_day,
    epr.week1_wood_tozai_cd,
    epr.week1_wood_late_sharpness,
    epr.week1_wood_haron_time_6,
    epr.week1_wood_haron_time_6_min,
    epr.week1_wood_lap_time_1_min,
    epr.week1_wood_accel_flag,
    epr.hanro_lap_time_1,
    epr.hanro_lap_time_2,
    epr.hanro_haron_time_4,
    epr.hanro_lap_time_1_z_tozai_day,
    epr.hanro_haron_time_4_z_tozai_day,
    epr.hanro_4f1f_profile_cat3,
    epr.hanro_tozai_cd,
    epr.hanro_late_sharpness,
    epr.hanro_haron_time_4_min,
    epr.hanro_lap_time_1_min,
    epr.hanro_accel_flag,
    epr.week1_hanro_lap_time_1,
    epr.week1_hanro_lap_time_2,
    epr.week1_hanro_haron_time_4,
    epr.week1_hanro_lap_time_1_z_tozai_day,
    epr.week1_hanro_haron_time_4_z_tozai_day,
    epr.week1_hanro_tozai_cd,
    epr.week1_hanro_late_sharpness,
    epr.week1_hanro_haron_time_4_min,
    epr.week1_hanro_lap_time_1_min,
    epr.week1_hanro_accel_flag,
    hpm.same_cluster_past_starts,
    hpm.same_cluster_first_start_flag,
    hpm.same_cluster_past_places,
    hpm.same_cluster_past_weighted_starts,
    hpm.same_cluster_past_weighted_pos4_agari_synergy,
    hpm.same_cluster_avg_pos4_agari_synergy,
    hpm.same_distance_past_starts,
    hpm.same_distance_past_weighted_places,
    hpm.same_distance_weighted_avg_pos4_agari_synergy,
    hpm.same_surface_condition_avg_pos4_agari_synergy,
    hpm.same_turn_direction_avg_pos4_agari_synergy,
    hpm.same_turn_direction_surface_past_starts,
    hpm.same_turn_direction_surface_avg_pos4_agari_synergy,
    hpm.same_homestretch_slope_surface_past_starts,
    hpm.same_homestretch_slope_surface_avg_pos4_agari_synergy,
    hpm.same_homestretch_slope_surface_wavg_pos4_agari_synergy,
    hpm.same_straight_distance_bucket_surface_past_starts,
    hpm.same_straight_distance_bucket_surface_avg_pos4_agari_synergy,
    hpm.same_straight_distance_bucket_surface_wavg_pos4_agari_synergy,
    hpm.pace_ntile1_place_rate,
    hpm.pace_ntile2_place_rate,
    hpm.pace_ntile3_place_rate,
    hpm.past_starts,
    hpm.past_places,
    jhpm.jockey_horse_pair_weighted_avg_pos4_agari_synergy,
    jhpm.jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
    jhpm.jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy,
    wpm.wood_4f1f_profile_place_rate_3y_smooth,
    wpm.hanro_4f1f_profile_place_rate_3y_smooth,
    wtlm.trainer_wood_lap_time_1_fast_excess_z_3y,
    wtlm.trainer_hanro_lap_time_1_fast_excess_z_3y,
    wtlm.trainer_week1_wood_lap_time_1_fast_excess_z_3y,
    wtlm.trainer_week1_hanro_lap_time_1_fast_excess_z_3y,
    wthm.trainer_wood_haron_time_4_fast_excess_z_3y,
    wthm.trainer_hanro_haron_time_4_fast_excess_z_3y,
    wthm.trainer_week1_wood_haron_time_4_fast_excess_z_3y,
    wthm.trainer_week1_hanro_haron_time_4_fast_excess_z_3y,
    csp.top3_corner3_pos_avg_5y,
    csp.top3_corner3_pos_var_5y,
    cp.cum_starts_5y,
    cp.diff_gate_pp_5y,
    cp.diff_gate_pp_std_5y,
    cp.p_place_5y,
    crs.course_style_place_rate_5y,
    csr.course_sashi_place_rate_5y,
    rrf.is_shokyu,
    rrf.race_level_diff,
    rrf.p1_race_level,
    rrf.is_jockey_change,
    rrf.distance_change,
    rrf.p1_distance_m,
    rrf.is_surface_changed,
    rrf.course_cluster_change,
    rrf.race_interval_days,
    rrf.p2_race_interval_days,
    rrf.horse_corner4_sd5,
    rrf.horse_corner4_trend5,
    rrf.pos4_agari_synergy_sd,
    rrf.horse_rel_agari3f_avg3,
    rrf.agari3f_rank_avg3,
    rrf.agari3f_rank_percentile_avg3,
    rrf.horse_rel_agari3f_avg5,
    rrf.horse_rel_agari3f_wavg5_recent,
    rrf.pos4_agari_synergy_avg3,
    rrf.pos4_agari_synergy_avg5,
    rrf.pos4_agari_synergy_wavg5_recent,
    rrf.pos4_agari_synergy_sd5,
    rrf.pos4_agari_synergy_trend5,
    rrf.p1_pos4_agari_synergy,
    rrf.p2_pos4_agari_synergy,
    rrf.p3_pos4_agari_synergy,
    rrf.p1_time_diff,
    rrf.p2_time_diff,
    rrf.p3_time_diff,
    rrf.p1_ten3f_vs_avg,
    rrf.p2_ten3f_vs_avg,
    rrf.p3_ten3f_vs_avg,
    rrf.ten3f_vs_avg_avg3,
    rrf.p1_pace_front_disadvantage,
    rrf.p2_pace_front_disadvantage,
    rrf.p3_pace_front_disadvantage,
    rrf.pace_front_disadvantage_avg3,
    rrf.p1_time_vs_pace_avg,
    rrf.p2_time_vs_pace_avg,
    rrf.p3_time_vs_pace_avg,
    rrf.time_diff_avg3,
    rrf.time_diff_avg5,
    rrf.time_diff_wavg5_recent,
    rrf.time_diff_sd5,
    rrf.time_diff_trend5,
    rrf.time_vs_pace_avg_avg3,
    rrf.time_vs_pace_avg_avg5,
    rrf.time_vs_pace_avg_wavg5_recent,
    rrf.time_vs_avg_avg5,
    rrf.time_vs_avg_wavg5_recent,
    rrf.time_vs_avg_sd5,
    rrf.time_vs_avg_trend5,
    rrf.time_vs_avg_adjusted_avg5,
    rrf.time_vs_avg_adjusted_wavg5_recent,
    rrf.time_diff_adjusted_avg5,
    rrf.time_vs_avg_sd,
    rrf.p1_corner4,
    rrf.p2_corner4,
    rrf.p3_corner4,
    rrf.horse_corner4_sd3,
    rrf.horse_kinryo_avg3,
    rrf.pos4_agari_synergy_slope3,
    rrf.pos4_agari_synergy_trend3_voladj,
    rrf.pos4_agari_synergy_short_long_gap,
    rrf.same_cluster_avg_pos4_agari_synergy_avg3,
    rrf.same_cluster_pos4_agari_synergy_diff,
    rrf.p1_wood_lap_time_1,
    rrf.p1_wood_lap_time_1_z_tozai_day,
    rrf.p1_trainer_wood_lap_time_1_fast_excess_z_3y,
    rrf.p1_hanro_lap_time_1,
    rrf.p1_hanro_lap_time_1_z_tozai_day,
    rrf.p1_trainer_hanro_lap_time_1_fast_excess_z_3y,
    rrf.jockey_avg_place_rate_avg3,
    rrf.jockey_avg_place_rate_avg3_smooth,
    rrf.p1_weight,
    rrf.p1_weight_change,
    rrf.weight_change_ratio,
    rrf.condition_change_score,
    rrf.distance_change_score,
    rrf.surface_change_score,
    rrf.jockey_place_rate_diff_ratio,
    rrf.jockey_place_rate_diff_ratio_smooth,
    rrf.num_past3_races,
    rrf.num_past5_races,
    rrf.course_cluster_change_score,
    rrf.p1_course_cluster,
    rrf.p1_jyo_cd,
    rrf.blinker_added,
    rrf.num_front_runners,
    rrf.pace_front_runners_avg,
    rrf.pace_front_runners_min,
    rrf.rel_agari_z,
    rrf.corner4_rate_z,
    rrf.corner4_rate_avg5_z,
    rrf.corner4_trend5_z,
    rrf.race_avg_corner4,
    rrf.race_stddev_corner4,
    rrf.race_styele_score,
    rrf.horse_styele_diff,
    rrf.style_score,
    rrf.time_vs_avg_z,
    rrf.time_vs_avg_avg5_z,
    rrf.time_vs_avg_wavg5_recent_z,
    rrf.time_vs_avg_wavg5_recent_diff_top_in_race,
    rrf.time_vs_avg_sd5_z,
    rrf.time_vs_avg_trend5_z,
    rrf.time_vs_pace_avg_z,
    rrf.time_vs_pace_avg_avg5_z,
    rrf.time_vs_pace_avg_wavg5_recent_z,
    rrf.time_vs_avg_diff_top_in_race,
    rrf.time_vs_avg_adjusted_z,
    rrf.time_vs_avg_adjusted_avg5_z,
    rrf.time_vs_avg_adjusted_wavg5_recent_z,
    rrf.time_vs_avg_adjusted_wavg5_recent_diff_top_in_race,
    rrf.time_vs_avg_adjusted_diff_top_in_race,
    rrf.time_diff_z,
    rrf.time_diff_robust,
    rrf.time_diff_avg5_z,
    rrf.time_diff_wavg5_recent_z,
    rrf.time_diff_wavg5_recent_robust,
    rrf.time_diff_wavg5_recent_diff_top_in_race,
    rrf.time_diff_wavg5_recent_rank,
    rrf.time_diff_sd5_z,
    rrf.time_diff_trend5_z,
    rrf.time_diff_rank,
    rrf.pos4_agari_synergy_z,
    rrf.pos4_agari_synergy_avg5_z,
    rrf.pos4_agari_synergy_wavg5_recent_z,
    rrf.race_pos4_agari_synergy_wavg5_recent_median,
    rrf.race_pos4_agari_synergy_wavg5_recent_iqr,
    rrf.pos4_agari_synergy_wavg5_recent_robust,
    rrf.pos4_agari_synergy_wavg5_recent_diff_top_in_race,
    rrf.pos4_agari_synergy_sd5_z,
    rrf.pos4_agari_synergy_trend5_z,
    rrf.pos4_agari_synergy_diff_top_in_race,
    rrf.pos4_agari_synergy_max_z,
    rrf.agari_good_z,
    rrf.rel_agari_min_z,
    rrf.same_cluster_avg_pos4_agari_synergy_z,
    rrf.same_turn_direction_surface_avg_pos4_agari_synergy_z,
    rrf.same_homestretch_slope_surface_avg_pos4_agari_synergy_z,
    rrf.same_distance_weighted_avg_pos4_agari_synergy_z,
    rrf.same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_z,
    rrf.same_cluster_avg_pos4_agari_synergy_rank,
    rrf.time_vs_avg_min_z,
    rrf.time_diff_adjusted_z,
    rrf.time_diff_adjusted_avg5_z,
    rrf.past_same_cluster_avg_pos4_as_z,
    rrf.age_days_z,
    rrf.kinryo_z,
    rrf.kinryo_adj_z,
    rrf.jockey_place_rate_z,
    rrf.jockey_place_rate_z_smooth,
    rrf.jockey_place_rate_3y_logit_z,
    rrf.jockey_place_rate_3y_logit_z_smooth,
    rrf.jockey_cluster_avg_place_rate_corrected_logit_z,
    rrf.jockey_cluster_avg_place_rate_corrected_rank,
    rrf.race_avg_jockey_place_rate,
    rrf.race_avg_jockey_place_rate_smooth,
    rrf.horse_corner4_avg3,
    rrf.horse_corner4_avg5,
    rrf.horse_corner4_wavg5_recent,
    rrf.running_style_avg3,
    rrf.running_style,
    least(
      greatest(
        coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3),
        0
      ),
      1
    ) as pred_pos4_for_jockey_te,
    case
      when coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3) is null then null
      when least(greatest(coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3), 0), 1) < 0.2 then 1
      when least(greatest(coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3), 0), 1) < 0.4 then 2
      when least(greatest(coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3), 0), 1) < 0.6 then 3
      when least(greatest(coalesce(rrf.horse_corner4_wavg5_recent, rrf.horse_corner4_avg5, rrf.horse_corner4_avg3), 0), 1) < 0.8 then 4
      else 5
    end as pred_pos4_bin5_hard,
    least(greatest(rrf.running_style_avg3, 1), 4) as pred_running_style_for_jockey_te,
    js.jockey_style_relative_place_rate_3y,
    js.jockey_style_relative_place_rate_3y_smooth,
    js.jockey_style_base_diff_logit_smooth,
    js.jockey_style_avg_diff_logit_smooth,
    js.jockey_style_place_rate_3y,
    js.jockey_style_place_rate_3y_smooth,
    js.jockey_style_place_rate_3y_style_prior_smooth,
    jss.jockey_surface_style_place_rate_3y_smooth,
    jo.jockey_starts_3y,
    jo.jockey_places_3y,
    jo.jockey_wins_3y,
    jo.jockey_place_rate_3y as jockey_avg_place_rate,
    jo.jockey_place_rate_3y_smooth as jockey_avg_place_rate_smooth,
    jo.jockey_place_rate_3y as jockey_avg_place_rate_corrected,
    jo.jockey_place_rate_3y_smooth as jockey_avg_place_rate_corrected_smooth,
    jo.jockey_place_rate_3y,
    jo.jockey_place_rate_3y_smooth,
    jo.jockey_place_rate_3y_logit,
    jo.jockey_place_rate_3y_logit_smooth,
    jc.jockey_cluster_starts_3y,
    jc.jockey_cluster_places_3y,
    jc.jockey_cluster_place_rate_3y as jockey_cluster_avg_place_rate_corrected,
    jc.jockey_cluster_place_rate_3y_smooth as jockey_cluster_avg_place_rate_corrected_smooth,
    jc.jockey_cluster_place_rate_3y - jo.jockey_place_rate_3y as jockey_cluster_avg_diff,
    jc.jockey_cluster_place_rate_3y_smooth - jo.jockey_place_rate_3y_smooth as jockey_cluster_avg_diff_smooth,
    jc.jockey_cluster_place_rate_3y,
    jc.jockey_cluster_place_rate_3y_smooth,
    jc.jockey_cluster_avg_diff_logit_smooth,
    jsd.jockey_surface_distance_starts_3y,
    jsd.jockey_surface_distance_places_3y,
    jsd.jockey_surface_distance_place_rate_3y,
    jsd.jockey_surface_distance_place_rate_3y_smooth,
    jsd.jockey_surface_dist_pm200_starts_3y,
    jsd.jockey_surface_dist_pm200_places_3y,
    jsd.jockey_surface_dist_pm200_place_rate_3y,
    jsd.jockey_surface_dist_pm200_place_rate_3y_smooth,
    jsj.jockey_surface_jyo_place_rate_3y_smooth,
    case
      when jsj.jockey_surface_jyo_place_rate_3y_smooth is null
        or jo.jockey_place_rate_3y_smooth is null then null
      else
        ln(
          least(greatest(jsj.jockey_surface_jyo_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jsj.jockey_surface_jyo_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
        -
        ln(
          least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
    end as jockey_surface_jyo_avg_diff_logit_smooth,
    jssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth,
    case
      when jssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth is null
        or jo.jockey_place_rate_3y_smooth is null then null
      else
        ln(
          least(greatest(jssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jssdb.jockey_surface_straight_distance_bucket_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
        -
        ln(
          least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
    end as jockey_surface_straight_distance_bucket_avg_diff_logit_smooth,
    jstd.jockey_surface_turn_direction_place_rate_3y_smooth,
    case
      when jstd.jockey_surface_turn_direction_place_rate_3y_smooth is null
        or jo.jockey_place_rate_3y_smooth is null then null
      else
        ln(
          least(greatest(jstd.jockey_surface_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jstd.jockey_surface_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
        -
        ln(
          least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
    end as jockey_surface_turn_direction_avg_diff_logit_smooth,
    jtd.jockey_turn_direction_place_rate_3y_smooth,
    case
      when jtd.jockey_turn_direction_place_rate_3y_smooth is null
        or jo.jockey_place_rate_3y_smooth is null then null
      else
        ln(
          least(greatest(jtd.jockey_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jtd.jockey_turn_direction_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
        -
        ln(
          least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(jo.jockey_place_rate_3y_smooth, 1e-6), 1 - 1e-6))
        )
    end as jockey_turn_direction_avg_diff_logit_smooth,
    coalesce(so.sire_starts_5y, 0) as sire_starts_5y,
    so.sire_places_5y,
    so.sire_avg_place_rate,
    so.sire_avg_place_rate_smooth,
    so.sire_avg_pos4_agari_synergy,
    so.sire_avg_time_diff,
    so.sire_career_months,
    so.sire_is_early_phase_3y,
    coalesce(sc.same_cluster_sire_starts_5y, 0) as same_cluster_sire_past_starts,
    sc.same_cluster_sire_places_5y,
    sc.same_cluster_sire_wins_5y,
    sc.same_cluster_sire_time_diffs_5y,
    case
      when sc.same_cluster_sire_starts_5y < 1 then null
      else sc.same_cluster_sire_places_5y::float / nullif(sc.same_cluster_sire_starts_5y, 0)
    end as same_cluster_sire_avg_place_rate,
    ((sc.same_cluster_sire_places_5y + (0.213 * 10))::float
      / nullif(sc.same_cluster_sire_starts_5y + 10, 0)) as same_cluster_sire_avg_place_rate_smooth,
    sc.same_cluster_sire_avg_pos4_agari_synergy,
    case
      when so.sire_avg_pos4_agari_synergy is null or sc.same_cluster_sire_avg_pos4_agari_synergy is null then null
      else sc.same_cluster_sire_avg_pos4_agari_synergy - so.sire_avg_pos4_agari_synergy
    end as same_cluster_sire_avg_pos4_agari_synergy_diff,
    case
      when so.sire_avg_place_rate_smooth is null
        or ((sc.same_cluster_sire_places_5y + (0.213 * 10))::float / nullif(sc.same_cluster_sire_starts_5y + 10, 0)) is null
        then null
      else
        ln(
          least(greatest(((sc.same_cluster_sire_places_5y + (0.213 * 10))::float / nullif(sc.same_cluster_sire_starts_5y + 10, 0)), 1e-6), 1 - 1e-6)
          / (1 - least(greatest(((sc.same_cluster_sire_places_5y + (0.213 * 10))::float / nullif(sc.same_cluster_sire_starts_5y + 10, 0)), 1e-6), 1 - 1e-6))
        )
        -
        ln(
          least(greatest(so.sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6)
          / (1 - least(greatest(so.sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6))
        )
    end as same_cluster_sire_avg_diff_logit,
    coalesce(sa.same_age_sire_starts_5y, 0) as same_age_sire_past_starts,
    sa.same_age_sire_places_5y,
    sa.age_place_rate_3y_prior,
    case
      when sa.same_age_sire_starts_5y < 1 then null
      else sa.same_age_sire_places_5y::float / nullif(sa.same_age_sire_starts_5y, 0)
    end as same_age_sire_avg_place_rate,
    sa.same_age_sire_avg_pos4_agari_synergy,
    coalesce(
      sa.same_age_sire_avg_place_rate_smooth_prev_age,
      ((sa.same_age_sire_places_5y + (so.sire_avg_place_rate_smooth * 20))::float
        / nullif(sa.same_age_sire_starts_5y + 20, 0))
    ) as same_age_sire_avg_place_rate_smooth,
    sa.same_age_sire_avg_place_rate_smooth_prev_age,
    coalesce(soc.same_old_cd_sire_starts_5y, 0) as same_old_cd_sire_past_starts,
    case
      when soc.same_old_cd_sire_starts_5y < 1 then null
      else soc.same_old_cd_sire_places_5y::float / nullif(soc.same_old_cd_sire_starts_5y, 0)
    end as same_old_cd_sire_avg_place_rate,
    soc.same_old_cd_sire_avg_pos4_agari_synergy,
    coalesce(
      soc.same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,
      ((soc.same_old_cd_sire_places_5y + (so.sire_avg_place_rate_smooth * 20))::float
        / nullif(soc.same_old_cd_sire_starts_5y + 20, 0))
    ) as same_old_cd_sire_avg_place_rate_smooth,
    soc.same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,
    ssc.same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd,
    ssc.same_sex_cd_sire_avg_pos4_agari_synergy,
    coalesce(sw.same_weight_sire_starts_5y, 0) as same_weight_sire_past_starts,
    sw.same_weight_sire_place_rate_5y as same_weight_sire_place_rate,
    ((sw.same_weight_sire_places_5y + (so.sire_avg_place_rate_smooth * 20))::float
      / nullif(sw.same_weight_sire_starts_5y + 20, 0)) as same_weight_sire_place_rate_smooth,
    coalesce(sdp.same_surface_dist_pm200_sire_starts_5y, 0) as same_surface_dist_pm200_sire_past_starts,
    case
      when sdp.same_surface_dist_pm200_sire_starts_5y < 1 then null
      else sdp.same_surface_dist_pm200_sire_places_5y::float
        / nullif(sdp.same_surface_dist_pm200_sire_starts_5y, 0)
    end as same_surface_dist_pm200_sire_avg_place_rate,
    sdp.same_surface_dist_pm200_sire_avg_pos4_agari_synergy,
    ((sdp.same_surface_dist_pm200_sire_places_5y + (so.sire_avg_place_rate_smooth * 20))::float
      / nullif(sdp.same_surface_dist_pm200_sire_starts_5y + 20, 0)) as same_surface_dist_pm200_sire_avg_place_rate_smooth,
    case
      when so.sire_avg_place_rate is null or sdp.same_surface_dist_pm200_sire_starts_5y < 1 then null
      else (
        sdp.same_surface_dist_pm200_sire_places_5y::float
        / nullif(sdp.same_surface_dist_pm200_sire_starts_5y, 0)
      ) - so.sire_avg_place_rate
    end as same_surface_dist_pm200_sire_avg_diff,
    coalesce(dy.dam_starts_5y, 0) as dam_starts_5y,
    dy.dam_avg_place_rate,
    dy.dam_avg_place_rate_smooth,
    dy.dam_avg_pos4_agari_synergy,
    dy.dam_avg_time_diff,
    coalesce(dc.same_cluster_dam_starts_5y, 0) as same_cluster_dam_past_starts,
    dc.same_cluster_dam_avg_place_rate,
    dc.same_cluster_dam_avg_place_rate_smooth,
    dc.same_cluster_dam_avg_pos4_agari_synergy,
    coalesce(dsy.damsire_starts_5y, 0) as damsire_starts_5y,
    dsy.damsire_avg_place_rate,
    dsy.damsire_avg_place_rate_smooth,
    dsy.damsire_avg_pos4_agari_synergy,
    dsy.damsire_avg_time_diff,
    coalesce(dsc.same_cluster_damsire_starts_5y, 0) as same_cluster_damsire_past_starts,
    dsc.same_cluster_damsire_avg_place_rate,
    dsc.same_cluster_damsire_avg_place_rate_smooth,
    dsc.same_cluster_damsire_avg_pos4_agari_synergy
  from context c
  left join trainer_stats ts
    on c.trainer_cd = ts.trainer_cd
   and c.held_year = ts.held_year
  left join trainer_old_stats tos
    on c.trainer_cd = tos.trainer_cd
   and c.old_cd = tos.old_cd
   and c.held_year = tos.held_year
  left join breeder_stats bs
    on c.breeder_cd = bs.breeder_cd
   and c.held_year = bs.held_year
  left join entry_pre_race epr
    on c.race_id = epr.race_id
   and c.kettonum = epr.kettonum
  left join horse_past_metrics hpm
    on c.kettonum = hpm.kettonum
   and c.held_date = hpm.held_date
  left join jockey_horse_pair_metrics jhpm
    on c.kettonum = jhpm.kettonum
   and c.jockey_cd = jhpm.jockey_cd
   and c.held_date = jhpm.held_date
  left join workout_profile_metrics wpm
    on c.race_id = wpm.race_id
   and c.kettonum = wpm.kettonum
  left join workout_trainer_lap_time_1_metrics wtlm
    on c.race_id = wtlm.race_id
   and c.kettonum = wtlm.kettonum
  left join workout_trainer_haron_time_4_metrics wthm
    on c.race_id = wthm.race_id
   and c.kettonum = wthm.kettonum
  left join course_style_profile csp
    on c.held_year = csp.held_year
   and c.jyo_cd = csp.jyo_cd
   and c.distance_m = csp.distance_m
   and c.surface = csp.surface
   and c.track_cd = csp.track_cd
  left join course_profile cp
    on c.held_year = cp.held_year
   and c.jyo_cd = cp.jyo_cd
   and c.distance_m = cp.distance_m
   and c.surface = cp.surface
   and c.track_cd = cp.track_cd
   and c.gate_number = cp.gate_number
  left join course_sashi_ratio csr
    on c.held_year = csr.held_year
   and c.jyo_cd = csr.jyo_cd
   and c.distance_m = csr.distance_m
   and c.surface = csr.surface
   and c.track_cd = csr.track_cd
  left join race_relative_features rrf
    on c.race_id = rrf.race_id
   and c.kettonum = rrf.kettonum
  left join course_running_style crs
    on c.held_year = crs.held_year
   and c.jyo_cd = crs.jyo_cd
   and c.distance_m = crs.distance_m
   and c.surface = crs.surface
   and c.track_cd = crs.track_cd
   and rrf.running_style = crs.running_style
  left join jockey_style js
    on c.jockey_cd = js.jockey_cd
   and c.held_year_month = js.held_year_month
   and rrf.running_style = js.running_style
  left join jockey_surface_style jss
    on c.jockey_cd = jss.jockey_cd
   and c.held_year_month = jss.held_year_month
   and c.surface = jss.surface
   and rrf.running_style = jss.running_style
  left join jockey_overall jo
    on c.jockey_cd = jo.jockey_cd
   and c.held_year_month = jo.held_year_month
  left join jockey_cluster jc
    on c.jockey_cd = jc.jockey_cd
   and c.held_year_month = jc.held_year_month
   and c.course_cluster = jc.course_cluster
  left join jockey_surface_distance jsd
    on c.jockey_cd = jsd.jockey_cd
   and c.held_year_month = jsd.held_year_month
   and c.surface = jsd.surface
   and c.distance_m = jsd.distance_m
  left join jockey_surface_jyo jsj
    on c.jockey_cd = jsj.jockey_cd
   and c.held_year_month = jsj.held_year_month
   and c.surface = jsj.surface
   and c.jyo_cd = jsj.jyo_cd
  left join jockey_surface_straight_distance_bucket jssdb
    on c.jockey_cd = jssdb.jockey_cd
   and c.held_year_month = jssdb.held_year_month
   and c.surface = jssdb.surface
   and c.straight_distance_bucket = jssdb.straight_distance_bucket
  left join jockey_surface_turn_direction jstd
    on c.jockey_cd = jstd.jockey_cd
   and c.held_year_month = jstd.held_year_month
   and c.surface = jstd.surface
   and c.turn_direction = jstd.turn_direction
  left join jockey_turn_direction jtd
    on c.jockey_cd = jtd.jockey_cd
   and c.held_year_month = jtd.held_year_month
   and c.turn_direction = jtd.turn_direction
  left join sire_overall so
    on c.sire_id = so.sire_id
   and c.held_year_month = so.held_year_month
  left join sire_cluster sc
    on c.sire_id = sc.sire_id
   and c.held_year_month = sc.held_year_month
   and c.course_cluster = sc.course_cluster
  left join sire_age sa
    on c.sire_id = sa.sire_id
   and c.held_year_month = sa.held_year_month
   and (case when c.age >= 8 then 8 else c.age end) = sa.age
  left join sire_old_cd soc
    on c.sire_id = soc.sire_id
   and c.held_year_month = soc.held_year_month
   and c.old_cd = soc.old_cd
  left join sire_sex_cd ssc
    on c.sire_id = ssc.sire_id
   and c.held_year_month = ssc.held_year_month
   and c.sex_cd = ssc.sex_cd
  left join sire_weight sw
    on c.sire_id = sw.sire_id
   and c.held_year_month = sw.held_year_month
   and c.h_weight_bin = sw.h_weight_bin
  left join sire_surface_distance_pm200 sdp
    on c.sire_id = sdp.sire_id
   and c.held_year_month = sdp.held_year_month
   and c.surface = sdp.surface
   and c.distance_m = sdp.distance_m
  left join dam_overall dy
    on c.dam_id = dy.dam_id
   and c.held_year_month = dy.held_year_month
  left join dam_cluster dc
    on c.dam_id = dc.dam_id
   and c.held_year_month = dc.held_year_month
   and c.course_cluster = dc.course_cluster
  left join damsire_overall dsy
    on c.damsire_id = dsy.damsire_id
   and c.held_year_month = dsy.held_year_month
  left join damsire_cluster dsc
    on c.damsire_id = dsc.damsire_id
   and c.held_year_month = dsc.held_year_month
   and c.course_cluster = dsc.course_cluster
),

feature_rows_with_jockey_te as (
  select
    fr.*,
    jpbh.jockey_pos4_bin5_starts_3y as jockey_pos4_bin5_starts_3y_hard,
    jpbh.jockey_pos4_bin5_place_rate_3y_smooth as jockey_pos4_bin5_place_rate_3y_smooth_hard,
    jpbh.jockey_pos4_bin5_relative_place_rate_3y_smooth as jockey_pos4_bin5_relative_place_rate_3y_smooth_hard,
    case
      when fr.pred_pos4_for_jockey_te is null then null
      else
        (w.weight1 * coalesce(jpbs1.jockey_pos4_bin5_starts_3y, 0))
        + (w.weight2 * coalesce(jpbs2.jockey_pos4_bin5_starts_3y, 0))
        + (w.weight3 * coalesce(jpbs3.jockey_pos4_bin5_starts_3y, 0))
        + (w.weight4 * coalesce(jpbs4.jockey_pos4_bin5_starts_3y, 0))
        + (w.weight5 * coalesce(jpbs5.jockey_pos4_bin5_starts_3y, 0))
    end as jockey_pos4_bin5_starts_3y_soft,
    case
      when fr.pred_pos4_for_jockey_te is null then null
      else
        (
          (case when jpbs1.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight1 * jpbs1.jockey_pos4_bin5_place_rate_3y_smooth end)
          + (case when jpbs2.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight2 * jpbs2.jockey_pos4_bin5_place_rate_3y_smooth end)
          + (case when jpbs3.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight3 * jpbs3.jockey_pos4_bin5_place_rate_3y_smooth end)
          + (case when jpbs4.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight4 * jpbs4.jockey_pos4_bin5_place_rate_3y_smooth end)
          + (case when jpbs5.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight5 * jpbs5.jockey_pos4_bin5_place_rate_3y_smooth end)
        ) / nullif(
          (case when jpbs1.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight1 end)
          + (case when jpbs2.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight2 end)
          + (case when jpbs3.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight3 end)
          + (case when jpbs4.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight4 end)
          + (case when jpbs5.jockey_pos4_bin5_place_rate_3y_smooth is null then 0 else w.weight5 end),
          0
        )
    end as jockey_pos4_bin5_place_rate_3y_smooth_soft,
    case
      when fr.pred_pos4_for_jockey_te is null then null
      else
        (
          (case when jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight1 * jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
          + (case when jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight2 * jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
          + (case when jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight3 * jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
          + (case when jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight4 * jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
          + (case when jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight5 * jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth end)
        ) / nullif(
          (case when jpbs1.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight1 end)
          + (case when jpbs2.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight2 end)
          + (case when jpbs3.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight3 end)
          + (case when jpbs4.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight4 end)
          + (case when jpbs5.jockey_pos4_bin5_relative_place_rate_3y_smooth is null then 0 else w.weight5 end),
          0
        )
    end as jockey_pos4_bin5_relative_place_rate_3y_smooth_soft,
    case
      when fr.pred_running_style_for_jockey_te is null then null
      else
        (
          (case when jssoft1.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight1 * jssoft1.jockey_style_place_rate_3y_smooth end)
          + (case when jssoft2.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight2 * jssoft2.jockey_style_place_rate_3y_smooth end)
          + (case when jssoft3.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight3 * jssoft3.jockey_style_place_rate_3y_smooth end)
          + (case when jssoft4.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight4 * jssoft4.jockey_style_place_rate_3y_smooth end)
        ) / nullif(
          (case when jssoft1.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight1 end)
          + (case when jssoft2.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight2 end)
          + (case when jssoft3.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight3 end)
          + (case when jssoft4.jockey_style_place_rate_3y_smooth is null then 0 else sw.weight4 end),
          0
        )
    end as jockey_style_place_rate_3y_smooth_soft
  from feature_rows fr
  left join jockey_pos4_bin jpbh
    on fr.jockey_cd = jpbh.jockey_cd
   and fr.held_year_month = jpbh.held_year_month
   and fr.pred_pos4_bin5_hard = jpbh.pos4_bin5
  left join jockey_pos4_bin jpbs1
    on fr.jockey_cd = jpbs1.jockey_cd
   and fr.held_year_month = jpbs1.held_year_month
   and jpbs1.pos4_bin5 = 1
  left join jockey_pos4_bin jpbs2
    on fr.jockey_cd = jpbs2.jockey_cd
   and fr.held_year_month = jpbs2.held_year_month
   and jpbs2.pos4_bin5 = 2
  left join jockey_pos4_bin jpbs3
    on fr.jockey_cd = jpbs3.jockey_cd
   and fr.held_year_month = jpbs3.held_year_month
   and jpbs3.pos4_bin5 = 3
  left join jockey_pos4_bin jpbs4
    on fr.jockey_cd = jpbs4.jockey_cd
   and fr.held_year_month = jpbs4.held_year_month
   and jpbs4.pos4_bin5 = 4
  left join jockey_pos4_bin jpbs5
    on fr.jockey_cd = jpbs5.jockey_cd
   and fr.held_year_month = jpbs5.held_year_month
   and jpbs5.pos4_bin5 = 5
  left join jockey_style jssoft1
    on fr.jockey_cd = jssoft1.jockey_cd
   and fr.held_year_month = jssoft1.held_year_month
   and jssoft1.running_style = 1
  left join jockey_style jssoft2
    on fr.jockey_cd = jssoft2.jockey_cd
   and fr.held_year_month = jssoft2.held_year_month
   and jssoft2.running_style = 2
  left join jockey_style jssoft3
    on fr.jockey_cd = jssoft3.jockey_cd
   and fr.held_year_month = jssoft3.held_year_month
   and jssoft3.running_style = 3
  left join jockey_style jssoft4
    on fr.jockey_cd = jssoft4.jockey_cd
   and fr.held_year_month = jssoft4.held_year_month
   and jssoft4.running_style = 4
  cross join lateral (
    select
      case when fr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(fr.pred_pos4_for_jockey_te - 0.1) / 0.2, 0) end as raw_weight1,
      case when fr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(fr.pred_pos4_for_jockey_te - 0.3) / 0.2, 0) end as raw_weight2,
      case when fr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(fr.pred_pos4_for_jockey_te - 0.5) / 0.2, 0) end as raw_weight3,
      case when fr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(fr.pred_pos4_for_jockey_te - 0.7) / 0.2, 0) end as raw_weight4,
      case when fr.pred_pos4_for_jockey_te is null then null else greatest(1 - abs(fr.pred_pos4_for_jockey_te - 0.9) / 0.2, 0) end as raw_weight5
  ) wr
  cross join lateral (
    select
      case when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null else wr.raw_weight1 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0)) end as weight1,
      case when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null else wr.raw_weight2 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0)) end as weight2,
      case when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null else wr.raw_weight3 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0)) end as weight3,
      case when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null else wr.raw_weight4 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0)) end as weight4,
      case when coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0) = 0 then null else wr.raw_weight5 / (coalesce(wr.raw_weight1, 0) + coalesce(wr.raw_weight2, 0) + coalesce(wr.raw_weight3, 0) + coalesce(wr.raw_weight4, 0) + coalesce(wr.raw_weight5, 0)) end as weight5
  ) w
  cross join lateral (
    select
      case when fr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(fr.pred_running_style_for_jockey_te - 1.0), 0) end as raw_weight1,
      case when fr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(fr.pred_running_style_for_jockey_te - 2.0), 0) end as raw_weight2,
      case when fr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(fr.pred_running_style_for_jockey_te - 3.0), 0) end as raw_weight3,
      case when fr.pred_running_style_for_jockey_te is null then null else greatest(1 - abs(fr.pred_running_style_for_jockey_te - 4.0), 0) end as raw_weight4
  ) swr
  cross join lateral (
    select
      case when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null else swr.raw_weight1 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0)) end as weight1,
      case when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null else swr.raw_weight2 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0)) end as weight2,
      case when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null else swr.raw_weight3 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0)) end as weight3,
      case when coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0) = 0 then null else swr.raw_weight4 / (coalesce(swr.raw_weight1, 0) + coalesce(swr.raw_weight2, 0) + coalesce(swr.raw_weight3, 0) + coalesce(swr.raw_weight4, 0)) end as weight4
  ) sw
)

select
  race_id,
  kettonum,
  held_date,
  held_year,
  held_year_month,
  held_month,
  horse_name,
  horse_number,
  gate_number,
  age,
  age_month,
  age_days,
  sex_cd,
  kinryo,
  kinryo_adj,
  tozai_cd,
  ensei_type,
  surface_condition_cd as surface_condition,
  weather_cd as tenko_cd,
  h_weight,
  h_weight_bin,
  weight_change,
  horse_number_ratio,
  jockey_cd,
  jockey_cat,
  jockey_starts_3y,
  jockey_places_3y,
  jockey_wins_3y,
  jockey_avg_place_rate,
  jockey_avg_place_rate_smooth,
  jockey_avg_place_rate_corrected,
  jockey_avg_place_rate_corrected_smooth,
  jockey_place_rate_3y,
  jockey_place_rate_3y_smooth,
  jockey_place_rate_3y_logit,
  jockey_place_rate_3y_logit_smooth,
  jockey_cluster_starts_3y,
  jockey_cluster_places_3y,
  jockey_cluster_avg_place_rate_corrected,
  jockey_cluster_avg_place_rate_corrected_smooth,
  jockey_cluster_avg_diff,
  jockey_cluster_avg_diff_smooth,
  jockey_cluster_place_rate_3y,
  jockey_cluster_place_rate_3y_smooth,
  jockey_cluster_avg_diff_logit_smooth,
  jockey_surface_distance_starts_3y,
  jockey_surface_distance_places_3y,
  jockey_surface_distance_place_rate_3y,
  jockey_surface_distance_place_rate_3y_smooth,
  jockey_surface_dist_pm200_starts_3y,
  jockey_surface_dist_pm200_places_3y,
  jockey_surface_dist_pm200_place_rate_3y,
  jockey_surface_dist_pm200_place_rate_3y_smooth,
  jockey_surface_jyo_place_rate_3y_smooth,
  jockey_surface_jyo_avg_diff_logit_smooth,
  jockey_surface_straight_distance_bucket_place_rate_3y_smooth,
  jockey_surface_straight_distance_bucket_avg_diff_logit_smooth,
  jockey_surface_turn_direction_place_rate_3y_smooth,
  jockey_surface_turn_direction_avg_diff_logit_smooth,
  jockey_turn_direction_place_rate_3y_smooth,
  jockey_turn_direction_avg_diff_logit_smooth,
  trainer_cd,
  trainer_cat,
  trainer_starts_5y,
  trainer_places_5y,
  trainer_place_rate_5y,
  trainer_old_starts_5y,
  trainer_old_places_5y,
  trainer_old_place_rate_5y,
  breeder_cd,
  breeder_cat,
  breeder_starts_5y,
  breeder_places_5y,
  breeder_wins_5y,
  breeder_place_rate_5y,
  breeder_place_rate_5y_smooth,
  dm_rank,
  wood_lap_time_1,
  wood_lap_time_2,
  wood_haron_time_4,
  wood_lap_time_1_z_tozai_day,
  wood_haron_time_4_z_tozai_day,
  wood_4f1f_profile_cat3,
  wood_tozai_cd,
  wood_late_sharpness,
  wood_haron_time_6,
  wood_haron_time_6_min,
  wood_lap_time_1_min,
  wood_accel_flag,
  week1_wood_lap_time_1,
  week1_wood_lap_time_2,
  week1_wood_haron_time_4,
  week1_wood_lap_time_1_z_tozai_day,
  week1_wood_haron_time_4_z_tozai_day,
  week1_wood_tozai_cd,
  week1_wood_late_sharpness,
  week1_wood_haron_time_6,
  week1_wood_haron_time_6_min,
  week1_wood_lap_time_1_min,
  week1_wood_accel_flag,
  hanro_lap_time_1,
  hanro_lap_time_2,
  hanro_haron_time_4,
  hanro_lap_time_1_z_tozai_day,
  hanro_haron_time_4_z_tozai_day,
  hanro_4f1f_profile_cat3,
  hanro_tozai_cd,
  hanro_late_sharpness,
  hanro_haron_time_4_min,
  hanro_lap_time_1_min,
  hanro_accel_flag,
  week1_hanro_lap_time_1,
  week1_hanro_lap_time_2,
  week1_hanro_haron_time_4,
  week1_hanro_lap_time_1_z_tozai_day,
  week1_hanro_haron_time_4_z_tozai_day,
  week1_hanro_tozai_cd,
  week1_hanro_late_sharpness,
  week1_hanro_haron_time_4_min,
  week1_hanro_lap_time_1_min,
  week1_hanro_accel_flag,
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
  same_homestretch_slope_surface_wavg_pos4_agari_synergy,
  same_straight_distance_bucket_surface_past_starts,
  same_straight_distance_bucket_surface_avg_pos4_agari_synergy,
  same_straight_distance_bucket_surface_wavg_pos4_agari_synergy,
  pace_ntile1_place_rate,
  pace_ntile2_place_rate,
  pace_ntile3_place_rate,
  past_starts,
  past_places,
  jockey_horse_pair_weighted_avg_pos4_agari_synergy,
  jockey_horse_pair_same_cluster_weighted_avg_pos4_agari_synergy,
  jockey_horse_pair_same_turn_dir_surface_wavg_pos4_agari_synergy,
  wood_4f1f_profile_place_rate_3y_smooth,
  hanro_4f1f_profile_place_rate_3y_smooth,
  trainer_wood_lap_time_1_fast_excess_z_3y,
  trainer_hanro_lap_time_1_fast_excess_z_3y,
  trainer_week1_wood_lap_time_1_fast_excess_z_3y,
  trainer_week1_hanro_lap_time_1_fast_excess_z_3y,
  trainer_wood_haron_time_4_fast_excess_z_3y,
  trainer_hanro_haron_time_4_fast_excess_z_3y,
  trainer_week1_wood_haron_time_4_fast_excess_z_3y,
  trainer_week1_hanro_haron_time_4_fast_excess_z_3y,
  top3_corner3_pos_avg_5y,
  top3_corner3_pos_var_5y,
  cum_starts_5y,
  diff_gate_pp_5y,
  diff_gate_pp_std_5y,
  p_place_5y,
  course_style_place_rate_5y,
  course_sashi_place_rate_5y,
  is_shokyu,
  race_level_diff,
  p1_race_level,
  is_jockey_change,
  distance_change,
  p1_distance_m,
  is_surface_changed,
  course_cluster_change,
  race_interval_days,
  p2_race_interval_days,
  horse_corner4_sd5,
  horse_corner4_trend5,
  pos4_agari_synergy_sd,
  horse_rel_agari3f_avg3,
  agari3f_rank_avg3,
  agari3f_rank_percentile_avg3,
  horse_rel_agari3f_avg5,
  horse_rel_agari3f_wavg5_recent,
  pos4_agari_synergy_avg3,
  pos4_agari_synergy_avg5,
  pos4_agari_synergy_wavg5_recent,
  pos4_agari_synergy_sd5,
  pos4_agari_synergy_trend5,
  p1_pos4_agari_synergy,
  p2_pos4_agari_synergy,
  p3_pos4_agari_synergy,
  p1_time_diff,
  p2_time_diff,
  p3_time_diff,
  p1_ten3f_vs_avg,
  p2_ten3f_vs_avg,
  p3_ten3f_vs_avg,
  ten3f_vs_avg_avg3,
  p1_pace_front_disadvantage,
  p2_pace_front_disadvantage,
  p3_pace_front_disadvantage,
  pace_front_disadvantage_avg3,
  p1_time_vs_pace_avg,
  p2_time_vs_pace_avg,
  p3_time_vs_pace_avg,
  time_diff_avg3,
  time_diff_avg5,
  time_diff_wavg5_recent,
  time_diff_sd5,
  time_diff_trend5,
  time_vs_pace_avg_avg3,
  time_vs_pace_avg_avg5,
  time_vs_pace_avg_wavg5_recent,
  time_vs_avg_avg5,
  time_vs_avg_wavg5_recent,
  time_vs_avg_sd5,
  time_vs_avg_trend5,
  time_vs_avg_adjusted_avg5,
  time_vs_avg_adjusted_wavg5_recent,
  time_diff_adjusted_avg5,
  time_vs_avg_sd,
  p1_corner4,
  p2_corner4,
  p3_corner4,
  horse_corner4_sd3,
  horse_kinryo_avg3,
  pos4_agari_synergy_slope3,
  pos4_agari_synergy_trend3_voladj,
  pos4_agari_synergy_short_long_gap,
  same_cluster_avg_pos4_agari_synergy_avg3,
  same_cluster_pos4_agari_synergy_diff,
  p1_wood_lap_time_1,
  p1_wood_lap_time_1_z_tozai_day,
  p1_trainer_wood_lap_time_1_fast_excess_z_3y,
  p1_hanro_lap_time_1,
  p1_hanro_lap_time_1_z_tozai_day,
  p1_trainer_hanro_lap_time_1_fast_excess_z_3y,
  jockey_avg_place_rate_avg3,
  jockey_avg_place_rate_avg3_smooth,
  p1_weight,
  p1_weight_change,
  weight_change_ratio,
  condition_change_score,
  distance_change_score,
  surface_change_score,
  jockey_place_rate_diff_ratio,
  jockey_place_rate_diff_ratio_smooth,
  num_past3_races,
  num_past5_races,
  course_cluster_change_score,
  p1_course_cluster,
  p1_jyo_cd,
  blinker_added,
  num_front_runners,
  pace_front_runners_avg,
  pace_front_runners_min,
  rel_agari_z,
  corner4_rate_z,
  corner4_rate_avg5_z,
  corner4_trend5_z,
  race_avg_corner4,
  race_stddev_corner4,
  race_styele_score,
  horse_styele_diff,
  style_score,
  time_vs_avg_z,
  time_vs_avg_avg5_z,
  time_vs_avg_wavg5_recent_z,
  time_vs_avg_wavg5_recent_diff_top_in_race,
  time_vs_avg_sd5_z,
  time_vs_avg_trend5_z,
  time_vs_pace_avg_z,
  time_vs_pace_avg_avg5_z,
  time_vs_pace_avg_wavg5_recent_z,
  time_vs_avg_diff_top_in_race,
  time_vs_avg_adjusted_z,
  time_vs_avg_adjusted_avg5_z,
  time_vs_avg_adjusted_wavg5_recent_z,
  time_vs_avg_adjusted_wavg5_recent_diff_top_in_race,
  time_vs_avg_adjusted_diff_top_in_race,
  time_diff_z,
  time_diff_robust,
  time_diff_avg5_z,
  time_diff_wavg5_recent_z,
  time_diff_wavg5_recent_robust,
  time_diff_wavg5_recent_diff_top_in_race,
  time_diff_wavg5_recent_rank,
  time_diff_sd5_z,
  time_diff_trend5_z,
  time_diff_rank,
  pos4_agari_synergy_z,
  pos4_agari_synergy_avg5_z,
  pos4_agari_synergy_wavg5_recent_z,
  race_pos4_agari_synergy_wavg5_recent_median,
  race_pos4_agari_synergy_wavg5_recent_iqr,
  pos4_agari_synergy_wavg5_recent_robust,
  pos4_agari_synergy_wavg5_recent_diff_top_in_race,
  pos4_agari_synergy_sd5_z,
  pos4_agari_synergy_trend5_z,
  pos4_agari_synergy_diff_top_in_race,
  pos4_agari_synergy_max_z,
  agari_good_z,
  rel_agari_min_z,
  same_cluster_avg_pos4_agari_synergy_z,
  same_turn_direction_surface_avg_pos4_agari_synergy_z,
  same_homestretch_slope_surface_avg_pos4_agari_synergy_z,
  same_distance_weighted_avg_pos4_agari_synergy_z,
  same_straight_distance_bucket_surface_wavg_pos4_agari_synergy_z,
  same_cluster_avg_pos4_agari_synergy_rank,
  time_vs_avg_min_z,
  time_diff_adjusted_z,
  time_diff_adjusted_avg5_z,
  past_same_cluster_avg_pos4_as_z,
  age_days_z,
  kinryo_z,
  kinryo_adj_z,
  jockey_place_rate_z,
  jockey_place_rate_z_smooth,
  jockey_place_rate_3y_logit_z,
  jockey_place_rate_3y_logit_z_smooth,
  jockey_cluster_avg_place_rate_corrected_logit_z,
  jockey_cluster_avg_place_rate_corrected_rank,
  race_avg_jockey_place_rate,
  race_avg_jockey_place_rate_smooth,
  horse_corner4_avg3,
  horse_corner4_avg5,
  horse_corner4_wavg5_recent,
  running_style_avg3,
  running_style,
  pred_pos4_for_jockey_te,
  pred_pos4_bin5_hard,
  pred_running_style_for_jockey_te,
  jockey_style_relative_place_rate_3y,
  jockey_style_relative_place_rate_3y_smooth,
  jockey_style_base_diff_logit_smooth,
  jockey_style_avg_diff_logit_smooth,
  jockey_style_place_rate_3y,
  jockey_style_place_rate_3y_smooth,
  jockey_style_place_rate_3y_style_prior_smooth,
  jockey_surface_style_place_rate_3y_smooth,
  jockey_pos4_bin5_starts_3y_hard,
  jockey_pos4_bin5_place_rate_3y_smooth_hard,
  jockey_pos4_bin5_relative_place_rate_3y_smooth_hard,
  jockey_pos4_bin5_starts_3y_soft,
  jockey_pos4_bin5_place_rate_3y_smooth_soft,
  jockey_pos4_bin5_relative_place_rate_3y_smooth_soft,
  jockey_style_place_rate_3y_smooth_soft,
  sire_id,
  sire_name,
  sire_cat,
  sire_starts_5y,
  sire_places_5y,
  sire_avg_place_rate,
  sire_avg_place_rate_smooth,
  sire_avg_pos4_agari_synergy,
  sire_avg_time_diff,
  sire_career_months,
  sire_is_early_phase_3y,
  same_cluster_sire_past_starts,
  same_cluster_sire_places_5y,
  same_cluster_sire_wins_5y,
  same_cluster_sire_time_diffs_5y,
  same_cluster_sire_avg_place_rate,
  same_cluster_sire_avg_place_rate_smooth,
  same_cluster_sire_avg_pos4_agari_synergy,
  same_cluster_sire_avg_pos4_agari_synergy_diff,
  same_cluster_sire_avg_diff_logit,
  same_age_sire_past_starts,
  same_age_sire_places_5y,
  age_place_rate_3y_prior,
  same_age_sire_avg_place_rate,
  same_age_sire_avg_place_rate_smooth,
  same_age_sire_avg_place_rate_smooth_prev_age,
  same_age_sire_avg_pos4_agari_synergy,
  same_old_cd_sire_past_starts,
  same_old_cd_sire_avg_place_rate,
  same_old_cd_sire_avg_place_rate_smooth,
  same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,
  same_old_cd_sire_avg_pos4_agari_synergy,
  same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd,
  same_sex_cd_sire_avg_pos4_agari_synergy,
  same_weight_sire_past_starts,
  same_weight_sire_place_rate,
  same_weight_sire_place_rate_smooth,
  same_surface_dist_pm200_sire_past_starts,
  same_surface_dist_pm200_sire_avg_place_rate,
  same_surface_dist_pm200_sire_avg_place_rate_smooth,
  same_surface_dist_pm200_sire_avg_pos4_agari_synergy,
  same_surface_dist_pm200_sire_avg_diff,
  dam_id,
  damsire_id,
  dam_starts_5y,
  dam_avg_place_rate,
  dam_avg_place_rate_smooth,
  dam_avg_pos4_agari_synergy,
  dam_avg_time_diff,
  same_cluster_dam_past_starts,
  same_cluster_dam_avg_place_rate,
  same_cluster_dam_avg_place_rate_smooth,
  same_cluster_dam_avg_pos4_agari_synergy,
  damsire_starts_5y,
  damsire_avg_place_rate,
  damsire_avg_place_rate_smooth,
  damsire_avg_pos4_agari_synergy,
  damsire_avg_time_diff,
  same_cluster_damsire_past_starts,
  same_cluster_damsire_avg_place_rate,
  same_cluster_damsire_avg_place_rate_smooth,
  same_cluster_damsire_avg_pos4_agari_synergy,
  birth_date,
  blinker_cd,
  race_name,
  round,
  jyo_cd,
  distance_m,
  surface,
  surface_condition_cd,
  weather_cd,
  jyuryo_cd,
  course_kubun_cd,
  old_cd,
  race_level,
  grade_cd,
  track_cd,
  hassotime,
  num_starters,
  planned_num_starters,
  course_cluster,
  turn_direction,
  turn_direction_cd,
  course_variant,
  straight_distance_m,
  straight_distance_bucket,
  elevation_diff_m,
  has_slope,
  has_homestretch_slope,
  has_uphill_finish,
  ijyo_cd,
  is_scratched,
  entry_status,
  is_prediction_target,
  updated_at
from feature_rows_with_jockey_te
