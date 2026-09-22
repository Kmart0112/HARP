{% macro normalize_jv_odds_v1(relation) %}
-- Only intermediate odds have MMDDHHMM. All-zero/blank times are not quotes.
-- Keep market sentinels as NULL; never drop a whole publication for one market.
with raw as (
  select
    year as source_year,
    to_date(trim(year) || lpad(trim(monthday), 4, '0'), 'YYYYMMDD') as held_date,
    concat(trim(year), lpad(trim(monthday),4,'0'), lpad(trim(jyocd),2,'0'),
           lpad(trim(kaiji),2,'0'), lpad(trim(nichiji),2,'0'), lpad(trim(racenum),2,'0'))::bigint as race_id,
    umaban::integer as horse_number,
    trim(happyotime) as publication_mmddhhmm,
    trim(tanodds) as win_raw, trim(fukuoddslow) as low_raw,
    trim(fukuoddshigh) as high_raw, trim(tanninki) as popularity_raw
  from {{ relation }}
  where nullif(trim(happyotime), '') is not null and trim(happyotime) <> '00000000'
), dated as (
  select *,
    source_year::integer + case
      when extract(month from held_date) = 1 and left(publication_mmddhhmm,2) = '12' then -1
      when extract(month from held_date) = 12 and left(publication_mmddhhmm,2) = '01' then 1
      else 0 end as publication_year
  from raw
)
select
  race_id, horse_number, held_date, source_year, publication_mmddhhmm,
  -- Timestamp without zone is explicitly interpreted in Japan time.
  case when publication_mmddhhmm ~ '^[0-9]{8}$' then
    make_timestamp(publication_year, substring(publication_mmddhhmm,1,2)::integer,
      substring(publication_mmddhhmm,3,2)::integer, substring(publication_mmddhhmm,5,2)::integer,
      substring(publication_mmddhhmm,7,2)::integer, 0) at time zone 'Asia/Tokyo'
    else ('invalid-publication:' || publication_mmddhhmm)::timestamptz
  end as odds_published_at,
  null::timestamptz as available_at,
  case when win_raw in ('', '----', '****', '0000') then null else win_raw::double precision / 10 end as odds_tansho,
  case when low_raw in ('', '----', '****', '0000') then null else low_raw::double precision / 10 end as odds_fukusho_low,
  case when high_raw in ('', '----', '****', '0000') then null else high_raw::double precision / 10 end as odds_fukusho_high,
  case when popularity_raw in ('', '--', '**', '00') then null else popularity_raw::integer end as popularity
from dated
{% endmacro %}
