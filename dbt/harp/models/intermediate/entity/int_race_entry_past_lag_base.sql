{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  tags=['feature', 'main']
) }}

with long_for_lag as (
  select
    f.race_id,
    f.kettonum,
    f.held_date,
    f.num_starters,
    f.surface,
    f.jyo_cd,
    f.distance_m,
    f.course_cluster,
    f.kinryo,
    f.h_weight,
    f.weight_change,
    f.time_diff,
    f.time_vs_avg,
    f.time_vs_pace_avg,
    f.agari3f_rank_in_race,
    f.agari3f_rank_percentile_in_race,
    f.ten3f_vs_avg,
    f.pace_front_disadvantage,
    f.race_level,
    f.old_cd,
    case
      when f.ten3f_vs_avg >= 1 then f.relative_agari3f
      else null
    end as relative_agari3f,
    f.sprint_decay,
    f.corner4_pos,
    f.pos4_agari_synergy,
    f.agari_good,
    f.time_diff_adjusted,
    f.jockey_cd,
    f.time_vs_avg + f.ten3f_vs_avg - 1.7 * f.ten4f_vs_avg as time_vs_avg_adjusted,
    f.ten4f_vs_avg_front_runners,
    f.running_style_cd,
    f.jockey_avg_place_rate,
    f.jockey_avg_place_rate_smooth,
    f.jockey_avg_place_rate_corrected,
    f.wood_lap_time_1,
    f.wood_lap_time_1_z_tozai_day,
    tm.trainer_wood_lap_time_1_fast_excess_z_3y,
    f.hanro_lap_time_1,
    f.hanro_lap_time_1_z_tozai_day,
    tm.trainer_hanro_lap_time_1_fast_excess_z_3y,
    f.blinker_cd
  from {{ ref('feat_race_entry_base') }} f
  left join {{ ref('feat_workout_trainer_lap_time_1_metrics') }} tm
    on f.race_id = tm.race_id
    and f.kettonum = tm.kettonum
  {% if is_incremental() %}
    where f.held_date >= current_date - interval '7 days'
  {% endif %}
),

with_cluster_info as (
  select
    l.*,
    cc.same_cluster_avg_pos4_agari_synergy
  from long_for_lag l
  left join {{ ref('int_horse_same_cluster_daily_cum') }} cc
    using (kettonum, held_date, course_cluster)
),

past_lag as (
  select
    race_id,
    kettonum,
    num_starters,
    corner4_pos,
    course_cluster,
    held_date,
    h_weight,
    distance_m,
    surface,
    jockey_avg_place_rate,
    jockey_avg_place_rate_smooth,
    jockey_avg_place_rate_corrected,
    same_cluster_avg_pos4_agari_synergy,
    lag(time_diff, 1) over w as p1_time_diff,
    lag(time_diff, 2) over w as p2_time_diff,
    lag(time_diff, 3) over w as p3_time_diff,
    lag(time_diff, 4) over w as p4_time_diff,
    lag(time_diff, 5) over w as p5_time_diff,
    lag(time_vs_avg, 1) over w as p1_time_vs_avg,
    lag(time_vs_avg, 2) over w as p2_time_vs_avg,
    lag(time_vs_avg, 3) over w as p3_time_vs_avg,
    lag(time_vs_avg, 4) over w as p4_time_vs_avg,
    lag(time_vs_avg, 5) over w as p5_time_vs_avg,
    lag(ten3f_vs_avg, 1) over w as p1_ten3f_vs_avg,
    lag(ten3f_vs_avg, 2) over w as p2_ten3f_vs_avg,
    lag(ten3f_vs_avg, 3) over w as p3_ten3f_vs_avg,
    lag(pace_front_disadvantage, 1) over w as p1_pace_front_disadvantage,
    lag(pace_front_disadvantage, 2) over w as p2_pace_front_disadvantage,
    lag(pace_front_disadvantage, 3) over w as p3_pace_front_disadvantage,
    lag(time_vs_pace_avg, 1) over w as p1_time_vs_pace_avg,
    lag(time_vs_pace_avg, 2) over w as p2_time_vs_pace_avg,
    lag(time_vs_pace_avg, 3) over w as p3_time_vs_pace_avg,
    lag(time_vs_pace_avg, 4) over w as p4_time_vs_pace_avg,
    lag(time_vs_pace_avg, 5) over w as p5_time_vs_pace_avg,
    lag(agari3f_rank_in_race, 1) over w as p1_agari3f_rank,
    lag(agari3f_rank_in_race, 2) over w as p2_agari3f_rank,
    lag(agari3f_rank_in_race, 3) over w as p3_agari3f_rank,
    lag(agari3f_rank_in_race, 4) over w as p4_agari3f_rank,
    lag(agari3f_rank_in_race, 5) over w as p5_agari3f_rank,
    lag(agari3f_rank_percentile_in_race, 1) over w as p1_agari3f_rank_percentile,
    lag(agari3f_rank_percentile_in_race, 2) over w as p2_agari3f_rank_percentile,
    lag(agari3f_rank_percentile_in_race, 3) over w as p3_agari3f_rank_percentile,
    lag(kinryo, 1) over w as p1_kinryo,
    lag(kinryo, 2) over w as p2_kinryo,
    lag(kinryo, 3) over w as p3_kinryo,
    lag(h_weight, 1) over w as p1_weight,
    lag(weight_change, 1) over w as p1_weight_change,
    lag(time_vs_avg_adjusted, 1) over w as p1_time_vs_avg_adjusted,
    lag(time_vs_avg_adjusted, 2) over w as p2_time_vs_avg_adjusted,
    lag(time_vs_avg_adjusted, 3) over w as p3_time_vs_avg_adjusted,
    lag(time_vs_avg_adjusted, 4) over w as p4_time_vs_avg_adjusted,
    lag(time_vs_avg_adjusted, 5) over w as p5_time_vs_avg_adjusted,
    lag(race_level, 1) over w as p1_race_level,
    lag(old_cd, 1) over w as p1_old_cd,
    lag(relative_agari3f, 1) over w as p1_rel_agari3f,
    lag(relative_agari3f, 2) over w as p2_rel_agari3f,
    lag(relative_agari3f, 3) over w as p3_rel_agari3f,
    lag(relative_agari3f, 4) over w as p4_rel_agari3f,
    lag(relative_agari3f, 5) over w as p5_rel_agari3f,
    lag(sprint_decay, 1) over w as p1_sprint_decay,
    lag(sprint_decay, 2) over w as p2_sprint_decay,
    lag(sprint_decay, 3) over w as p3_sprint_decay,
    lag(corner4_pos, 1) over w as p1_corner4,
    lag(corner4_pos, 2) over w as p2_corner4,
    lag(corner4_pos, 3) over w as p3_corner4,
    lag(corner4_pos, 4) over w as p4_corner4,
    lag(corner4_pos, 5) over w as p5_corner4,
    stddev_samp(corner4_pos) over (
      partition by kettonum
      order by held_date, race_id
      rows between 3 preceding and 1 preceding
    ) as horse_corner4_sd3,
    lag(pos4_agari_synergy, 1) over w as p1_pos4_agari_synergy,
    lag(pos4_agari_synergy, 2) over w as p2_pos4_agari_synergy,
    lag(pos4_agari_synergy, 3) over w as p3_pos4_agari_synergy,
    lag(pos4_agari_synergy, 4) over w as p4_pos4_agari_synergy,
    lag(pos4_agari_synergy, 5) over w as p5_pos4_agari_synergy,
    lag(agari_good, 1) over w as p1_agari_good,
    lag(agari_good, 2) over w as p2_agari_good,
    lag(agari_good, 3) over w as p3_agari_good,
    lag(same_cluster_avg_pos4_agari_synergy, 1) over w as p1_same_cluster_avg_pos4_agari_synergy,
    lag(same_cluster_avg_pos4_agari_synergy, 2) over w as p2_same_cluster_avg_pos4_agari_synergy,
    lag(same_cluster_avg_pos4_agari_synergy, 3) over w as p3_same_cluster_avg_pos4_agari_synergy,
    (held_date::date - lag(held_date, 1) over w)::int as race_interval_days,
    (held_date::date - lag(held_date, 2) over w)::int as p2_race_interval_days,
    (held_date::date - lag(held_date, 3) over w)::int as p3_race_interval_days,
    lag(time_diff_adjusted, 1) over w as p1_time_diff_adjusted,
    lag(time_diff_adjusted, 2) over w as p2_time_diff_adjusted,
    lag(time_diff_adjusted, 3) over w as p3_time_diff_adjusted,
    lag(time_diff_adjusted, 4) over w as p4_time_diff_adjusted,
    lag(time_diff_adjusted, 5) over w as p5_time_diff_adjusted,
    lag(ten4f_vs_avg_front_runners, 1) over w as p1_ten4f_vs_avg_front_runners,
    lag(ten4f_vs_avg_front_runners, 2) over w as p2_ten4f_vs_avg_front_runners,
    lag(ten4f_vs_avg_front_runners, 3) over w as p3_ten4f_vs_avg_front_runners,
    lag(running_style_cd, 1) over w as p1_running_style_cd,
    lag(running_style_cd, 2) over w as p2_running_style_cd,
    lag(running_style_cd, 3) over w as p3_running_style_cd,
    lag(distance_m, 1) over w as p1_distance_m,
    lag(distance_m, 2) over w as p2_distance_m,
    lag(distance_m, 3) over w as p3_distance_m,
    lag(jyo_cd, 1) over w as p1_jyo_cd,
    lag(jyo_cd, 2) over w as p2_jyo_cd,
    lag(jyo_cd, 3) over w as p3_jyo_cd,
    lag(surface, 1) over w as p1_surface,
    lag(surface, 2) over w as p2_surface,
    lag(surface, 3) over w as p3_surface,
    lag(course_cluster, 1) over w as p1_course_cluster,
    lag(course_cluster, 2) over w as p2_course_cluster,
    lag(course_cluster, 3) over w as p3_course_cluster,
    lag(wood_lap_time_1, 1) over w as p1_wood_lap_time_1,
    lag(wood_lap_time_1_z_tozai_day, 1) over w as p1_wood_lap_time_1_z_tozai_day,
    lag(trainer_wood_lap_time_1_fast_excess_z_3y, 1) over w as p1_trainer_wood_lap_time_1_fast_excess_z_3y,
    lag(hanro_lap_time_1, 1) over w as p1_hanro_lap_time_1,
    lag(hanro_lap_time_1_z_tozai_day, 1) over w as p1_hanro_lap_time_1_z_tozai_day,
    lag(trainer_hanro_lap_time_1_fast_excess_z_3y, 1) over w as p1_trainer_hanro_lap_time_1_fast_excess_z_3y,
    case
      when lag(surface, 1) over w is null then null
      when surface = lag(surface, 1) over w then 0
      else 1
    end as is_surface_changed,
    coalesce((race_level > lag(race_level, 1) over w)::int, 0) as is_shokyu,
    coalesce(race_level - lag(race_level, 1) over w, 0) as race_level_diff,
    coalesce((jockey_cd != lag(jockey_cd, 1) over w)::int, 0) as is_jockey_change,
    lag(jockey_avg_place_rate, 1) over w as p1_jockey_avg_place_rate,
    lag(jockey_avg_place_rate, 2) over w as p2_jockey_avg_place_rate,
    lag(jockey_avg_place_rate, 3) over w as p3_jockey_avg_place_rate,
    lag(jockey_avg_place_rate_smooth, 1) over w as p1_jockey_avg_place_rate_smooth,
    lag(jockey_avg_place_rate_smooth, 2) over w as p2_jockey_avg_place_rate_smooth,
    lag(jockey_avg_place_rate_smooth, 3) over w as p3_jockey_avg_place_rate_smooth,
    case
      when lag(blinker_cd, 1) over w = 0 and blinker_cd = 1 then 1
      else 0
    end as blinker_added
  from with_cluster_info
  window w as (
    partition by kettonum
    order by held_date, race_id
  )
)

select *
from past_lag
