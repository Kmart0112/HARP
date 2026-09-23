{% set feature_input_mode = var('feature_input_mode', var('feature_snapshot_mode', 'training')) %}

{% if feature_input_mode not in ['training', 'latest', 'all'] %}
  {{ exceptions.raise_compiler_error("feature_input_mode must be one of: training, latest, all") }}
{% endif %}

{% set include_live_context = feature_input_mode in ['latest', 'all'] %}
{% set include_training_context = feature_input_mode in ['training', 'all'] %}
{% set is_live_context = feature_input_mode == 'latest' %}

{% if execute and flags.FULL_REFRESH and (
  feature_input_mode != 'training'
  or var('target_held_date', none) is not none
  or var('race_from_date', none) is not none
  or var('race_to_date', none) is not none
) %}
  {{ exceptions.raise_compiler_error(
    'feat_race_entry_pre_race full refresh requires feature_input_mode=training without date filters. '
    ~ 'Use an incremental run for a target day/period so stored NN histories are retained.'
  ) }}
{% endif %}

{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  on_schema_change='sync_all_columns',
  tags=['feature_matrix', 'race_day_live', 'training', 'nn_inputs'],
  indexes=[
    {'columns': ['race_id', 'kettonum'], 'unique': True},
    {'columns': ['held_date']}
  ]
) }}

-- depends_on: {{ ref('int_race_day_feature_context') }}
-- depends_on: {{ ref('int_race_entry_feature_context') }}

-- Shared pre-race values. Keep entity windows and smoothing identical to LightGBM.
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
)

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
    csr.course_sashi_place_rate_5y,
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
