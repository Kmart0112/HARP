{% macro nn_pre_race_feature_columns() %}
  {# Ordered model inputs shared by current entries and historical runs.
     Entity identifiers, lifecycle state, odds and outcomes are deliberately absent. #}
  {{ return([
    'horse_number', 'gate_number', 'age', 'age_month', 'sex_cd',
    'kinryo', 'kinryo_adj', 'h_weight', 'weight_change', 'blinker_cd',
    'jyo_cd', 'distance_m', 'surface', 'surface_condition_cd', 'weather_cd',
    'old_cd', 'race_level', 'grade_cd', 'track_cd', 'num_starters',
    'turn_direction_cd', 'straight_distance_m', 'elevation_diff_m',
    'has_homestretch_slope', 'held_month', 'ensei_type',
    'wood_lap_time_1', 'wood_haron_time_4',
    'wood_lap_time_1_z_tozai_day', 'wood_haron_time_4_z_tozai_day',
    'hanro_lap_time_1', 'hanro_haron_time_4',
    'hanro_lap_time_1_z_tozai_day', 'hanro_haron_time_4_z_tozai_day',
    'week1_wood_lap_time_1', 'week1_wood_haron_time_4',
    'week1_hanro_lap_time_1', 'week1_hanro_haron_time_4',
    'jockey_starts_3y', 'jockey_place_rate_3y_smooth',
    'jockey_cluster_starts_3y', 'jockey_cluster_place_rate_3y_smooth',
    'jockey_surface_dist_pm200_starts_3y', 'jockey_surface_dist_pm200_place_rate_3y_smooth',
    'trainer_starts_5y', 'trainer_place_rate_5y',
    'breeder_starts_5y', 'breeder_place_rate_5y_smooth',
    'sire_starts_5y', 'sire_avg_place_rate_smooth', 'sire_avg_pos4_agari_synergy',
    'same_cluster_sire_past_starts', 'same_cluster_sire_avg_place_rate_smooth',
    'dam_starts_5y', 'dam_avg_place_rate_smooth', 'dam_avg_pos4_agari_synergy',
    'damsire_starts_5y', 'damsire_avg_place_rate_smooth', 'damsire_avg_pos4_agari_synergy'
  ]) }}
{% endmacro %}

{% macro nn_select_pre_race_features(alias) %}
  {% for column in nn_pre_race_feature_columns() %}
    {{ alias }}.{{ column }}{% if not loop.last %},{% endif %}
  {% endfor %}
{% endmacro %}

{% macro nn_select_stats_metadata(alias) %}
  {# These are cutoffs, not source publication/receipt timestamps. #}
  {{ alias }}.held_year_month::date as monthly_stats_cutoff,
  make_date({{ alias }}.held_year::int, 1, 1) as yearly_stats_cutoff,
  {{ alias }}.jockey_place_rate_3y_smooth is null as jockey_stats_missing,
  {{ alias }}.trainer_place_rate_5y is null as trainer_stats_missing,
  {{ alias }}.breeder_place_rate_5y_smooth is null as breeder_stats_missing,
  {{ alias }}.sire_avg_place_rate_smooth is null as sire_stats_missing,
  {{ alias }}.dam_avg_place_rate_smooth is null as dam_stats_missing,
  {{ alias }}.damsire_avg_place_rate_smooth is null as damsire_stats_missing
{% endmacro %}
