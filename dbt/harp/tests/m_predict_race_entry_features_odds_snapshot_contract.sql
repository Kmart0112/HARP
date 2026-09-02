with expected_columns(column_name) as (
  values ('odds_snapshot_type')
),

actual_columns as (
  select column_name
  from information_schema.columns
  where table_schema = '{{ ref("m_predict_race_entry_features").schema }}'
    and table_name = '{{ ref("m_predict_race_entry_features").identifier }}'
),

missing_expected as (
  select column_name
  from expected_columns
  except
  select column_name
  from actual_columns
),

forbidden_columns as (
  select column_name
  from actual_columns
  where column_name = 'feature_snapshot_type'
),

invalid_values as (
  select odds_snapshot_type::text as column_name
  from {{ ref('m_predict_race_entry_features') }}
  where odds_snapshot_type <> 'latest'
  group by 1
)

select * from missing_expected
union all
select * from forbidden_columns
union all
select * from invalid_values
