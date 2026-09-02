#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cognee-env.sh"

if [[ "$#" -lt 1 ]]; then
  echo "usage: scripts/cognee-search.sh <query text>" >&2
  exit 2
fi

QUERY_TYPE="${COGNEE_QUERY_TYPE:-GRAPH_COMPLETION}"
TOP_K="${COGNEE_TOP_K:-5}"
OUTPUT_FORMAT="${COGNEE_OUTPUT_FORMAT:-pretty}"
DATASET_NAME="${HARP_COGNEE_DATASET}"

exec uv run --extra knowledge cognee-cli search \
  --datasets "${DATASET_NAME}" \
  --query-type "${QUERY_TYPE}" \
  --top-k "${TOP_K}" \
  --output-format "${OUTPUT_FORMAT}" \
  "$*"
