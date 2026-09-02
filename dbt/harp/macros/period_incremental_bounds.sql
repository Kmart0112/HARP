{% macro monthly_incremental_bounds(this_relation, period_column='held_year_month', history_years=3) %}
  {% if is_incremental() %}
    select
      coalesce(max({{ period_column }}), '1900-01-01'::timestamp) as max_period,
      (
        coalesce(max({{ period_column }}), '1900-01-01'::timestamp)
        - make_interval(months => {{ var('monthly_incremental_recalc_months') }})
      )::timestamp as recalc_from_period,
      (
        coalesce(max({{ period_column }}), '1900-01-01'::timestamp)
        - make_interval(months => {{ var('monthly_incremental_recalc_months') }})
        - make_interval(years => {{ history_years }})
      )::timestamp as hist_from_period
    from {{ this_relation }}
  {% else %}
    select
      null::timestamp as max_period,
      null::timestamp as recalc_from_period,
      null::timestamp as hist_from_period
  {% endif %}
{% endmacro %}

{% macro yearly_incremental_bounds(this_relation, period_column='held_year', history_years=5) %}
  {% set recalc_years = var('yearly_incremental_recalc_years') | int %}
  {% set total_history_years = recalc_years + (history_years | int) %}
  {% if is_incremental() %}
    select
      coalesce(max({{ period_column }}), 1900) as max_period,
      (coalesce(max({{ period_column }}), 1900) - {{ recalc_years }})::int as recalc_from_period,
      (coalesce(max({{ period_column }}), 1900) - {{ total_history_years }})::int as hist_from_period
    from {{ this_relation }}
  {% else %}
    select
      null::int as max_period,
      null::int as recalc_from_period,
      null::int as hist_from_period
  {% endif %}
{% endmacro %}
