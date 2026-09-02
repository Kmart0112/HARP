{{ config(
    materialized='table',
    unique_key='race_id',
    on_schema_change='sync_all_columns'
) }}

with base as (
  select * ,
    case 
      when grade_cd = 'A' then 'G1'
      when grade_cd = 'B' then 'G2'
      when grade_cd = 'C' then 'G3'
      when grade_cd = 'D' then 'OP' 
      when grade_cd = 'E' then 'OP'
      else null
    end as grade_code,

    case
      when  jyokencd1 != '000' then jyokencd1
      when  jyokencd2 != '000' then jyokencd2
      when  jyokencd3 != '000' then jyokencd3
      when  jyokencd4 != '000' then jyokencd4
      when  jyokencd5 != '000' then jyokencd5
      else null
    end  as jyoken_code
  from {{ ref('stg_s_race') }}
),

final as (
  select
    -- race_id: year+monthday+jyo+kaiji+nichiji+racenum
    concat(
      year,
      monthday,
      lpad(trim(jyocd), 2, '0'),
      lpad(kaiji::text, 2, '0'),
      lpad(nichiji::text, 2, '0'),
      lpad(racenum::text, 2, '0')
    )::bigint  as race_id,

    racenum as race_round,

    to_date(year || monthday, 'YYYYMMDD') as held_date,

    trim(concat_ws(' ', hondai, fukudai, kakko)) as name,

    nullif(trim(jyocd), '')::int as jyo_cd,
    kaiji,
    nichiji,
    racenum as race_num,

    -- 今はコードそのまま（あとで辞書で名称にしてもOK）
    jyocd as course,

    case
      when sibababacd != '0' then '0'
      when dirtbabacd != '0' then '1'
      else null
    end ::int
    as surface,
    case
      when sibababacd != '0' then sibababacd
      when dirtbabacd != '0' then dirtbabacd
      else null
    end ::int as surface_condition,

    case
      when syubetu_cd = '11' then '1'
      when syubetu_cd = '12' then '2'
      else '0'
    end ::int as old_cd,

    kyori as distance_m,
    gradecd as grade_cd,

    syussotosu::int as num_starters,
    track_cd,

    now() as updated_at

  from base
)

select * from final
where held_date > '2012-01-01'

-- {% if is_incremental() %}
-- -- ざっくり増分：開催日で絞る（生データの更新特性次第で調整）
-- -- where to_date(year || monthday, 'YYYYMMDD') >= (select coalesce(max(held_date), '1900-01-01'::date) from {{ this }})
-- {% endif %}
