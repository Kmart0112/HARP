{{ config(
    materialized='table',
    schema='sokuho',
)}}

select
*
from {{ ref('stg_s_uma_race') }} as src