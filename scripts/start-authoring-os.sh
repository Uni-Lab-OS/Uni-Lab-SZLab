#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
core_root="$(cd "${repo_root}/.." && pwd)"
unilab_os_root="${UNILAB_OS_ROOT:-${core_root}/Uni-Lab-OS}"
unilab_python="${UNILAB_PYTHON:-python}"
runtime_dir="${UNILAB_SZLAB_RUNTIME_DIR:-${repo_root}/runtime/authoring}"

mkdir -p "${runtime_dir}"
export PYTHONPATH="${unilab_os_root}:${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${unilab_python}" -m unilabos.app.main \
  --workspace "${repo_root}" \
  --graph "${repo_root}/deployment/graphs/szlab-local-debug.json" \
  --config "${repo_root}/deployment/local_config.py" \
  --working_dir "${runtime_dir}" \
  --backend simple \
  --app_bridges fastapi \
  --port "${UNILAB_OS_PORT:-8014}" \
  --disable_browser \
  --skip_env_check \
  --test_mode
