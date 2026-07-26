#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_python="${UNILAB_PYTHON:-python}"
dist_dir="${UNILAB_PACKAGE_DIST_DIR:-${repo_root}/dist/szlab}"

mkdir -p "${dist_dir}"
exec "${unilab_python}" -m pip wheel \
  --no-deps \
  --no-build-isolation \
  --wheel-dir "${dist_dir}" \
  "${repo_root}/packages/szlab_poly_studio"
