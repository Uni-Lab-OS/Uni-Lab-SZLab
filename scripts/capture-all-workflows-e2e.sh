#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${UNILAB_E2E_HEADED:-0}" != "1" ]]; then
  exec env UNILAB_E2E_HEADED=1 \
    xvfb-run -a node "${repo_root}/e2e/capture-all-workflows.mjs"
fi

exec node "${repo_root}/e2e/capture-all-workflows.mjs"
