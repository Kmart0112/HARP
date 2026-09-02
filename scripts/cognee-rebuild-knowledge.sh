#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/cognee-env.sh"

KNOWLEDGE_ROOT="${1:-docs/knowledge}"
DATASET_NAME="${2:-${HARP_COGNEE_DATASET}}"

if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "LLM_API_KEY is empty. Fill it in .env.local before rebuilding the Cognee dataset." >&2
  exit 2
fi

if [[ ! -d "${KNOWLEDGE_ROOT}" ]]; then
  echo "knowledge root not found: ${KNOWLEDGE_ROOT}" >&2
  exit 2
fi

KNOWLEDGE_ROOT_ABS="$(cd "${KNOWLEDGE_ROOT}" && pwd)"
mapfile -d '' KNOWLEDGE_FILES < <(
  find "${KNOWLEDGE_ROOT_ABS}" -type f \( -name '*.md' -o -name '*.yml' -o -name '*.yaml' \) -print0 | sort -z
)

if [[ "${#KNOWLEDGE_FILES[@]}" -eq 0 ]]; then
  echo "no knowledge files found under ${KNOWLEDGE_ROOT_ABS}" >&2
  exit 2
fi

uv run --extra knowledge cognee-cli add --dataset-name "${DATASET_NAME}" "${KNOWLEDGE_FILES[@]}"
exec uv run --extra knowledge cognee-cli cognify --datasets "${DATASET_NAME}"
