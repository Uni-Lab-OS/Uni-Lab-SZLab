#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
core_root="$(cd "${repo_root}/.." && pwd)"
unilab_os_root="${UNILAB_OS_ROOT:-${core_root}/Uni-Lab-OS}"
unilab_python="${UNILAB_PYTHON:-python}"
runtime_dir="${UNILAB_SZLAB_RUNTIME_DIR:-${repo_root}/runtime}"

mkdir -p "${runtime_dir}"
export PYTHONPATH="${unilab_os_root}:${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${unilab_python}" "${repo_root}/deployment/local_bridge_entrypoint.py" \
  --host 127.0.0.1 \
  --schedule-port "${UNILAB_SCHEDULE_PORT:-8890}" \
  --api-port "${UNILAB_API_PORT:-8014}" \
  --journal-path "${runtime_dir}/quick-debug.sqlite3" \
  --profile "${repo_root}/szlab_poly_studio/profiles/default/package.yaml"
