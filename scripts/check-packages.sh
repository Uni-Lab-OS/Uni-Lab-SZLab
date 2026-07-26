#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_command="${UNILAB_COMMAND:-unilab}"

for package_name in szlab_poly_studio ai4c_robot; do
  package_root="${repo_root}/packages/${package_name}"
  (
    cd "${package_root}"
    "${unilab_command}" \
      --check_mode \
      --devices "./${package_name}" \
      --external_devices_only
  )
done
