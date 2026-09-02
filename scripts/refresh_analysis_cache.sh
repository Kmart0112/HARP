#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

skip_dbt=0
full_refresh=0
skip_odds=0
dbt_target=""
train_year_start=2013
test_year=2025
selector="training_default"
main_output=""
odds_output=""

usage() {
  cat <<'EOF'
Usage: scripts/refresh_analysis_cache.sh [options]

Refresh the standard analysis parquet cache after dbt.

Options:
  --skip-dbt                Skip dbt build and only refresh parquet outputs
  --full-refresh            Pass -f to dbt build
  --target <name>           Optional dbt target name
  --train-year-start <yr>   Lower bound year for main parquet export (default: 2013)
  --test-year <yr>          Suffix year for main parquet file name (default: 2025)
  --main-output <path>      Override main parquet output path
  --odds-output <path>      Override odds parquet output path
  --skip-odds               Skip exporting core.fct_race_odds_result
  --help                    Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-dbt)
      skip_dbt=1
      shift
      ;;
    --full-refresh)
      full_refresh=1
      shift
      ;;
    --target)
      dbt_target="${2:-}"
      shift 2
      ;;
    --train-year-start)
      train_year_start="${2:-}"
      shift 2
      ;;
    --test-year)
      test_year="${2:-}"
      shift 2
      ;;
    --main-output)
      main_output="${2:-}"
      shift 2
      ;;
    --odds-output)
      odds_output="${2:-}"
      shift 2
      ;;
    --skip-odds)
      skip_odds=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${main_output}" ]]; then
  main_output="notebook/tmp/analysis_cache/m_train_race_horse_past5_${train_year_start}_${test_year}.parquet"
fi
if [[ -z "${odds_output}" ]]; then
  odds_output="notebook/tmp/analysis_cache/race_odds.parquet"
fi

run_cmd() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

cd "${PROJECT_ROOT}"

if [[ "${skip_dbt}" -eq 0 ]]; then
  dbt_cmd=(
    uv tool run --isolated --from dbt-core==1.10.0 --with dbt-postgres==1.9.1
    dbt build
    --project-dir dbt/harp
    --profiles-dir dbt/harp
    --no-version-check
    --selector "${selector}"
  )
  if [[ "${full_refresh}" -eq 1 ]]; then
    dbt_cmd+=(-f)
  fi
  if [[ -n "${dbt_target}" ]]; then
    dbt_cmd+=(--target "${dbt_target}")
  fi
  run_cmd "${dbt_cmd[@]}"
fi

run_cmd \
  env PYTHONPATH=src \
  uv run python -m pipeline.jobs.export_table_to_parquet \
  --source-table mart.m_train_race_horse_past5 \
  --output "${main_output}" \
  --where "held_date__gte=${train_year_start}-01-01" \
  --where "race_level__gte=1" \
  --where "race_level__lte=3" \
  --overwrite

if [[ "${skip_odds}" -eq 0 ]]; then
  run_cmd \
    env PYTHONPATH=src \
    uv run python -m pipeline.jobs.export_table_to_parquet \
    --source-table core.fct_race_odds_result \
    --output "${odds_output}" \
    --overwrite
fi
