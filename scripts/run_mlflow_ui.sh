#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HARP_ENV="${HARP_ENV:-local}"
DEFAULT_BACKEND_STORE_URI="${REPO_ROOT}/mlflow"
MLFLOW_UI_HOST="${HARP_MLFLOW_UI_HOST:-127.0.0.1}"
MLFLOW_UI_PORT="${HARP_MLFLOW_UI_PORT:-5050}"

load_env_file() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

resolve_backend_store_uri() {
  local tracking_uri="${HARP_MLFLOW_TRACKING_URI:-}"

  if [[ -z "${tracking_uri}" ]]; then
    printf '%s\n' "${DEFAULT_BACKEND_STORE_URI}"
    return 0
  fi

  if [[ "${tracking_uri}" == file://* ]]; then
    python3 - "${tracking_uri}" <<'PY'
from pathlib import Path
from urllib.parse import unquote, urlparse
import sys

uri = sys.argv[1]
parsed = urlparse(uri)
path = unquote(parsed.path or "")
if parsed.netloc and parsed.netloc not in {"", "localhost"}:
    path = f"//{parsed.netloc}{path}"
print(str(Path(path).resolve()))
PY
    return 0
  fi

  printf '%s\n' "${tracking_uri}"
}

cd "${REPO_ROOT}"
load_env_file "${REPO_ROOT}/.env.${HARP_ENV}"
load_env_file "${REPO_ROOT}/.env"

BACKEND_STORE_URI="$(resolve_backend_store_uri)"

printf 'Starting MLflow UI\n'
printf 'backend-store-uri: %s\n' "${BACKEND_STORE_URI}"
printf 'url: http://%s:%s\n' "${MLFLOW_UI_HOST}" "${MLFLOW_UI_PORT}"

exec uv run mlflow ui \
  --backend-store-uri "${BACKEND_STORE_URI}" \
  --host "${MLFLOW_UI_HOST}" \
  --port "${MLFLOW_UI_PORT}"
