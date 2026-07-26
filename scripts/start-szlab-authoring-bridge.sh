#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
core_root="$(cd "${repo_root}/.." && pwd)"
unilab_os_root="${UNILAB_OS_ROOT:-${core_root}/Uni-Lab-OS}"
unilab_python="${UNILAB_PYTHON:-python}"
runtime_dir="${UNILAB_SZLAB_RUNTIME_DIR:-${repo_root}/runtime/szlab}"

mkdir -p "${runtime_dir}"
export PYTHONPATH="${unilab_os_root}:${repo_root}/packages/szlab_poly_studio${PYTHONPATH:+:${PYTHONPATH}}"

exec "${unilab_python}" -m unilabos.app.local_bridge.server \
  --host 127.0.0.1 \
  --schedule-port "${UNILAB_SCHEDULE_PORT:-8890}" \
  --api-port "${UNILAB_API_PORT:-8014}" \
  --journal-path "${runtime_dir}/quick-debug.sqlite3" \
  --profile "${repo_root}/packages/szlab_poly_studio/package.yaml" \
  --graph "${repo_root}/deployment/graphs/szlab-local-debug.json" \
  --offline
