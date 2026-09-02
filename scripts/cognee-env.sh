#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env.local" ]]; then
  set -a
  source "${ROOT_DIR}/.env.local"
  set +a
fi

HARP_COGNEE_SYSTEM_ROOT="${HARP_COGNEE_SYSTEM_ROOT:-outputs/cognee/system}"
HARP_COGNEE_DATA_ROOT="${HARP_COGNEE_DATA_ROOT:-outputs/cognee/data}"

export SYSTEM_ROOT_DIRECTORY="${ROOT_DIR}/${HARP_COGNEE_SYSTEM_ROOT#./}"
export DATA_ROOT_DIRECTORY="${ROOT_DIR}/${HARP_COGNEE_DATA_ROOT#./}"
export VECTOR_DB_PROVIDER="${VECTOR_DB_PROVIDER:-lancedb}"
export GRAPH_DATABASE_PROVIDER="${GRAPH_DATABASE_PROVIDER:-kuzu}"
export ENABLE_BACKEND_ACCESS_CONTROL="${ENABLE_BACKEND_ACCESS_CONTROL:-false}"
export LLM_PROVIDER="${LLM_PROVIDER:-openai}"
export LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"
export HARP_COGNEE_DATASET="${HARP_COGNEE_DATASET:-harp_knowledge}"

mkdir -p "${SYSTEM_ROOT_DIRECTORY}" "${DATA_ROOT_DIRECTORY}"

cd "${ROOT_DIR}"
