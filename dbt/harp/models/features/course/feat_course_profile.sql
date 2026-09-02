-- 年×コースで直近5年の統計を取る
{{ config(
  materialized='incremental',
  unique_key=['jyo_cd', 'distance_m', 'surface', 'track_cd', 'gate_number', 'held_year'],
  indexes=[{'columns': ['held_year', 'jyo_cd', 'distance_m', 'surface', 'track_cd', 'gate_number']}],
  tags=['feature']
) }}

with incremental_bounds as (
  {{ yearly_incremental_bounds(this, history_years=5) }}
),

races as (
    select
        race_id,
        held_date,
        held_year,
        jyo_cd,
        distance_m,
        course_cluster,
        surface,
        track_cd,
        surface_condition_cd,
        time_sec_race,
        race_pace,
        gate_number,
        running_style_cd,
        is_place
    from {{ ref('int_race_entry_enriched') }}
    where num_starters >= 12
      and race_level in (1, 2, 3, 4)
      and old_cd = 0
    {% if is_incremental() %}
      and held_year >= (select hist_from_period from incremental_bounds)
    {% endif %}
),

yarly_overall_course_pp as (
    select
        jyo_cd,
        distance_m,
        surface,
        track_cd,
        held_year,
        count(*) as starts,
        sum(is_place) as places,
        sum(is_place)::float / nullif(count(*), 0) as p_place_overall
    from races
    group by jyo_cd, distance_m, surface, track_cd, held_year
),

overall_course_pp_cum as (
    select
        yoc.jyo_cd,
        yoc.distance_m,
        yoc.surface,
        yoc.track_cd,
        yoc.held_year,
        sum(yoc.starts) over (
          partition by yoc.jyo_cd, yoc.distance_m, yoc.surface, yoc.track_cd
          order by yoc.held_year
          rows between 5 preceding and 1 preceding
        ) as cum_starts_5y,
        sum(yoc.places) over (
          partition by yoc.jyo_cd, yoc.distance_m, yoc.surface, yoc.track_cd
          order by yoc.held_year
          rows between 5 preceding and 1 preceding
        ) as cum_places_5y
    from yarly_overall_course_pp yoc
),

yearly_course_gate_pp as (
    select
        held_year,
        jyo_cd,
        distance_m,
        surface,
        track_cd,
        gate_number,
        count(*) as starts,
        sum(is_place) as places,
        sum(is_place)::float / nullif(count(*), 0) as p_place
    from races
    group by held_year, jyo_cd, distance_m, surface, track_cd, gate_number
),

yearly_gate_gap_pp as (
    select
        ycg.jyo_cd,
        ycg.distance_m,
        ycg.surface,
        ycg.track_cd,
        ycg.gate_number,
        ycg.held_year,
        ycg.starts,
        ycg.places,
        ycg.p_place,
        ocp.p_place_overall,
        ycg.p_place / nullif(ocp.p_place_overall, 0) as diff_gate_pp
    from yearly_course_gate_pp ycg
    left join yarly_overall_course_pp ocp
      on ycg.jyo_cd = ocp.jyo_cd
     and ycg.distance_m = ocp.distance_m
     and ycg.surface = ocp.surface
     and ycg.track_cd = ocp.track_cd
     and ycg.held_year = ocp.held_year
),

overall_course_pp as (
    select
        occ.jyo_cd,
        occ.distance_m,
        occ.surface,
        occ.track_cd,
        occ.held_year,
        case
          when occ.cum_starts_5y > 0 then occ.cum_places_5y::float / occ.cum_starts_5y
          else null
        end as p_place_5y
    from overall_course_pp_cum occ
),

yearly_gate_gap_pp_cum as (
    select
        ycg.held_year,
        ycg.jyo_cd,
        ycg.distance_m,
        ycg.surface,
        ycg.track_cd,
        ycg.gate_number,
        ycg.starts as starts_on_conditions,
        sum(ycg.starts) over (
          partition by ycg.jyo_cd, ycg.distance_m, ycg.surface, ycg.track_cd, ycg.gate_number
          order by ycg.held_year
          rows between 5 preceding and 1 preceding
        ) as cum_starts_5y,
        avg(diff_gate_pp) over (
          partition by ycg.jyo_cd, ycg.distance_m, ycg.surface, ycg.track_cd, ycg.gate_number
          order by ycg.held_year
          rows between 5 preceding and 1 preceding
        ) as diff_gate_pp_5y,
        stddev(diff_gate_pp) over (
          partition by ycg.jyo_cd, ycg.distance_m, ycg.surface, ycg.track_cd, ycg.gate_number
          order by ycg.held_year
          rows between 5 preceding and 1 preceding
        ) as diff_gate_pp_std_5y
    from yearly_gate_gap_pp ycg
)

select
    yg.jyo_cd,
    yg.distance_m,
    yg.surface,
    yg.track_cd,
    yg.gate_number,
    yg.held_year,
    yg.cum_starts_5y,
    yg.diff_gate_pp_5y,
    yg.diff_gate_pp_std_5y,
    ocp.p_place_5y
from yearly_gate_gap_pp_cum yg
left join overall_course_pp ocp
  on yg.jyo_cd = ocp.jyo_cd
 and yg.distance_m = ocp.distance_m
 and yg.surface = ocp.surface
 and yg.track_cd = ocp.track_cd
 and yg.held_year = ocp.held_year
{% if is_incremental() %}
where yg.held_year >= (select recalc_from_period from incremental_bounds)
{% endif %}
