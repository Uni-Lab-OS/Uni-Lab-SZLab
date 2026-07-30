#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_command="${UNILAB_COMMAND:-unilab}"

cd "${repo_root}/packages/ai4c_robot"
exec "${unilab_command}" \
  --check_mode \
  --devices "./ai4c_robot" \
  --external_devices_only
