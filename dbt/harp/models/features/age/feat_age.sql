-- 年齢ごとの複勝率
{{ config(materialized='table', tags=['feature']) }}

with base as (
	select
		age,
		is_place
	from {{ ref('int_race_entry_enriched') }}
	where age is not null
),

age_summary as (
	select
		age,
		count(*) as starts,
		sum(is_place) as places
	from base
	group by
		age
)

select
	age,
	starts,
	places,
	places::float / nullif(starts, 0) as place_rate
from age_summary
