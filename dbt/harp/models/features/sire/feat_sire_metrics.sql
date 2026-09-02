{{ config(
  materialized='incremental',
  unique_key=['race_id', 'kettonum'],
  tags=['feature'],
  indexes=[
    {'columns': ['race_id', 'kettonum']}
  ]
) }}

with incremental_bounds as (
  {% if is_incremental() %}
    select
      coalesce(max(frh.held_date), '1900-01-01'::date) as max_held_date,
      (
        coalesce(max(frh.held_date), '1900-01-01'::date)
        - ({{ var('incremental_recalc_days') }} * interval '1 day')
      )::date as recalc_from_date
    from {{ this }} t
    left join {{ ref('feat_race_entry_base') }} frh
      on t.race_id = frh.race_id
      and t.kettonum = frh.kettonum
  {% else %}
    select
      null::date as max_held_date,
      null::date as recalc_from_date
  {% endif %}
),

long as (
  select
    race_id,
    kettonum,
    sire_id,
    held_year_month,
    course_cluster,
    sex_cd,
    old_cd,
    surface,
    distance_m,
    case
      when distance_m < 1400 then 1
      when distance_m < 1800 then 2
      when distance_m < 2200 then 3
      else 4
    end as distance_bucket_cd,
    h_weight_bin,
    age
  from {{ ref('feat_race_entry_base') }}
  {% if is_incremental() %}
    where held_date >= (select recalc_from_date from incremental_bounds)
  {% endif %}
),

sire_yearly_overall as (
  select
    *
  from {{ ref('feat_sire_yearly_overall') }}
),

sire_yearly_cluster as (
  select
    *
  from {{ ref('feat_sire_yearly_cluster') }}
),

sire_yearly_age as (
  select
    *
  from {{ ref('feat_sire_yearly_age') }}
),

sire_yearly_old_cd as (
  select
    *
  from {{ ref('feat_sire_yearly_old_cd') }}
),

sire_yearly_sex_cd as (
  select
    *
  from {{ ref('feat_sire_yearly_sex_cd') }}
),

sire_yearly_weight as (
  select
    *
  from {{ ref('feat_sire_weight') }}
),

sire_yearly_surface_distance_pm200 as (
  select
    *
  from {{ ref('feat_sire_yearly_surface_distance_pm200') }}
),

sire_metrics as (
  select
    l.race_id,
    l.kettonum,
    coalesce(sire_starts_5y, 0) as sire_starts_5y,
    ds.sire_career_months,
    ds.sire_is_early_phase_3y,
    ds.sire_avg_place_rate,
    ds.sire_avg_place_rate_smooth,
    ds.sire_avg_pos4_agari_synergy,
    ds.sire_avg_time_diff,
    age_place_rate_3y_prior,
    so.old_cd_place_rate_3y_prior,

    case when cs.same_cluster_sire_starts_5y < 1 then null
      else (cs.same_cluster_sire_places_5y)::float
        / (cs.same_cluster_sire_starts_5y) end as same_cluster_sire_avg_place_rate,

    ((cs.same_cluster_sire_places_5y + ( 0.213 * 10))::float
      / nullif(cs.same_cluster_sire_starts_5y + 10, 0)) as same_cluster_sire_avg_place_rate_smooth,
    cs.same_cluster_sire_avg_pos4_agari_synergy,

    coalesce(cs.same_cluster_sire_starts_5y, 0) as same_cluster_sire_past_starts,

    coalesce(sa.same_age_sire_starts_5y, 0) as same_age_sire_past_starts,
    sa.same_age_sire_avg_place_rate_smooth_prev_age,

    case when sa.same_age_sire_starts_5y < 1 then null
      else
        (sa.same_age_sire_places_5y)::float
        / (sa.same_age_sire_starts_5y)
    end as same_age_sire_avg_place_rate,
    sa.same_age_sire_avg_pos4_agari_synergy,

    coalesce(
      sa.same_age_sire_avg_place_rate_smooth_prev_age,
      ((sa.same_age_sire_places_5y + (ds.sire_avg_place_rate_smooth * 20))::float
        / nullif(sa.same_age_sire_starts_5y + 20, 0))
    ) as same_age_sire_avg_place_rate_smooth,

    coalesce(so.same_old_cd_sire_starts_5y, 0) as same_old_cd_sire_past_starts,
    so.same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,

    case when so.same_old_cd_sire_starts_5y < 1 then null
      else
        (so.same_old_cd_sire_places_5y)::float
        / (so.same_old_cd_sire_starts_5y)
    end as same_old_cd_sire_avg_place_rate,
    so.same_old_cd_sire_avg_pos4_agari_synergy,
    ss.same_sex_cd_sire_avg_place_rate_smooth_prev_sex_cd,
    ss.same_sex_cd_sire_avg_pos4_agari_synergy,

    coalesce(
      so.same_old_cd_sire_avg_place_rate_smooth_prev_old_cd,
      ((so.same_old_cd_sire_places_5y + (ds.sire_avg_place_rate_smooth * 20))::float
        / nullif(so.same_old_cd_sire_starts_5y + 20, 0))
    ) as same_old_cd_sire_avg_place_rate_smooth,


    sw.same_weight_sire_place_rate_5y,

    coalesce(sw.same_weight_sire_starts_5y, 0) as same_weight_sire_past_starts,

    ((sw.same_weight_sire_places_5y + ( ds.sire_avg_place_rate_smooth * 20))::float
      / nullif(sw.same_weight_sire_starts_5y + 20, 0)) as same_weight_sire_place_rate_5y_smooth,

    coalesce(sdp.same_surface_dist_pm200_sire_starts_5y, 0) as same_surface_dist_pm200_sire_past_starts,
    case
      when sdp.same_surface_dist_pm200_sire_starts_5y < 1 then null
      else sdp.same_surface_dist_pm200_sire_places_5y::float / nullif(sdp.same_surface_dist_pm200_sire_starts_5y, 0)
    end as same_surface_dist_pm200_sire_avg_place_rate,
    sdp.same_surface_dist_pm200_sire_avg_pos4_agari_synergy,
    ((sdp.same_surface_dist_pm200_sire_places_5y + (ds.sire_avg_place_rate_smooth * 20))::float
      / nullif(sdp.same_surface_dist_pm200_sire_starts_5y + 20, 0)) as same_surface_dist_pm200_sire_avg_place_rate_smooth


  from long l
  left join sire_yearly_cluster cs
    on l.sire_id = cs.sire_id
    and l.course_cluster = cs.course_cluster
    and l.held_year_month = cs.held_year_month
  left join sire_yearly_age sa
    on l.sire_id = sa.sire_id
    and (case when l.age >= 8 then 8 else l.age end) = sa.age
    and l.held_year_month = sa.held_year_month
  left join sire_yearly_old_cd so
    on l.sire_id = so.sire_id
    and l.old_cd = so.old_cd
    and l.held_year_month = so.held_year_month
  left join sire_yearly_sex_cd ss
    on l.sire_id = ss.sire_id
    and l.sex_cd = ss.sex_cd
    and l.held_year_month = ss.held_year_month
  left join sire_yearly_overall ds
    on l.sire_id = ds.sire_id
    and l.held_year_month = ds.held_year_month
  left join sire_yearly_weight sw
    on l.sire_id = sw.sire_id
    and l.held_year_month = sw.held_year_month
    and sw.h_weight_bin = l.h_weight_bin
  left join sire_yearly_surface_distance_pm200 sdp
    on l.sire_id = sdp.sire_id
    and l.held_year_month = sdp.held_year_month
    and l.surface = sdp.surface
    and l.distance_m = sdp.distance_m

)

select
  sm.*,
  case when sm.sire_avg_place_rate is null or sm.same_cluster_sire_avg_place_rate is null then null
    else sm.same_cluster_sire_avg_place_rate - sm.sire_avg_place_rate
  end as same_cluster_sire_avg_diff,
  case when sm.sire_avg_place_rate is null or sm.same_age_sire_avg_place_rate is null then null
    else sm.same_age_sire_avg_place_rate - sm.sire_avg_place_rate
  end as same_age_sire_avg_diff,
  case when sm.sire_avg_place_rate is null or sm.same_old_cd_sire_avg_place_rate is null then null
    else sm.same_old_cd_sire_avg_place_rate - sm.sire_avg_place_rate
  end as same_old_cd_sire_avg_diff,
  case when sm.sire_avg_place_rate is null or sm.same_surface_dist_pm200_sire_avg_place_rate is null then null
    else sm.same_surface_dist_pm200_sire_avg_place_rate - sm.sire_avg_place_rate
  end as same_surface_dist_pm200_sire_avg_diff,
  case
    when sm.sire_avg_pos4_agari_synergy is null or sm.same_cluster_sire_avg_pos4_agari_synergy is null then null
    else sm.same_cluster_sire_avg_pos4_agari_synergy - sm.sire_avg_pos4_agari_synergy
  end as same_cluster_sire_avg_pos4_agari_synergy_diff,
  case
    when sm.sire_avg_place_rate_smooth is null or sm.same_cluster_sire_avg_place_rate_smooth is null then null
    else
      ln(
        least(greatest(sm.same_cluster_sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.same_cluster_sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(sm.sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.sire_avg_place_rate_smooth, 1e-6), 1 - 1e-6))
      )
  end as same_cluster_sire_avg_diff_logit,
  case
    when sm.sire_avg_place_rate is null or sm.same_age_sire_avg_place_rate is null then null
    else
      ln(
        least(greatest(sm.same_age_sire_avg_place_rate, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.same_age_sire_avg_place_rate, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(sm.sire_avg_place_rate, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.sire_avg_place_rate, 1e-6), 1 - 1e-6))
      )
  end as same_age_sire_avg_diff_logit
  ,
  case
    when sm.sire_avg_place_rate is null or sm.same_old_cd_sire_avg_place_rate is null then null
    else
      ln(
        least(greatest(sm.same_old_cd_sire_avg_place_rate, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.same_old_cd_sire_avg_place_rate, 1e-6), 1 - 1e-6))
      )
      -
      ln(
        least(greatest(sm.sire_avg_place_rate, 1e-6), 1 - 1e-6)
        / (1 - least(greatest(sm.sire_avg_place_rate, 1e-6), 1 - 1e-6))
      )
  end as same_old_cd_sire_avg_diff_logit
from sire_metrics sm
