#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_command="${UNILAB_COMMAND:-unilab}"

cd "${repo_root}/packages/szlab_poly_studio"
exec "${unilab_command}" \
  --check_mode \
  --devices "./szlab_poly_studio" \
  --external_devices_only
