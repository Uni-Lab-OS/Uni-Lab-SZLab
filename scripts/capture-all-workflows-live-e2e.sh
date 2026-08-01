#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

curl --fail-with-body --silent --show-error \
  "${UNILAB_FE_E2E_URL:-http://127.0.0.1:5173}/" \
  >/dev/null
curl --fail-with-body --silent --show-error \
  "${UNILAB_OS_E2E_URL:-http://127.0.0.1:8015}/health" \
  >/dev/null
curl --fail-with-body --silent --show-error \
  "${UNILAB_EDGE_ACTIONS_URL:-http://127.0.0.1:18003/internal/v1/runtime-actions}" \
  >/dev/null

exec node "${repo_root}/e2e/capture-all-workflows-live.mjs"
