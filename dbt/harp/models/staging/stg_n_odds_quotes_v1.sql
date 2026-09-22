{{ config(materialized='view', tags=['odds_contract_v1']) }}
{{ normalize_jv_odds_v1(source('raw', 'n_jodds_tanpuku')) }}

