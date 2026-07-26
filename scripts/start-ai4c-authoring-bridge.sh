#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
core_root="$(cd "${repo_root}/.." && pwd)"
unilab_os_root="${UNILAB_OS_ROOT:-${core_root}/Uni-Lab-OS}"
unilab_python="${UNILAB_PYTHON:-python}"
runtime_dir="${UNILAB_AI4C_RUNTIME_DIR:-${repo_root}/runtime/ai4c}"

mkdir -p "${runtime_dir}"
export PYTHONPATH="${unilab_os_root}:${repo_root}/packages/ai4c_robot${PYTHONPATH:+:${PYTHONPATH}}"

exec "${unilab_python}" -m unilabos.app.local_bridge.server \
  --host 127.0.0.1 \
  --schedule-port "${UNILAB_SCHEDULE_PORT:-8890}" \
  --api-port "${UNILAB_API_PORT:-8014}" \
  --journal-path "${runtime_dir}/quick-debug.sqlite3" \
  --profile "${repo_root}/packages/ai4c_robot/package.yaml" \
  --graph "${repo_root}/deployment/graphs/ai4c-local-debug.json" \
  --offline
