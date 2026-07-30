#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${UNILAB_SZLAB_RUNTIME_DIR:-${repo_root}/runtime/os}"
unilab_command="${UNILAB_COMMAND:-unilab}"

mkdir -p "${runtime_dir}"

exec "${unilab_command}" \
  --graph "${repo_root}/deployment/graphs/local-debug.json" \
  --config "${repo_root}/deployment/local_config.py" \
  --working_dir "${runtime_dir}" \
  --devices "${repo_root}/packages/szlab_poly_studio/szlab_poly_studio" \
  --devices "${repo_root}/packages/ai4c_robot/ai4c_robot" \
  --profile "${repo_root}/packages/szlab_poly_studio/package.yaml" \
  --profile "${repo_root}/packages/ai4c_robot/package.yaml" \
  --external_devices_only \
  --backend ros \
  --app_bridges fastapi \
  --port "${UNILAB_OS_PORT:-18002}" \
  --schedule_addr "ws://127.0.0.1:${UNILAB_SCHEDULE_PORT:-8890}/api/v1/ws/schedule" \
  --disable_browser \
  --skip_env_check \
  --test_mode
