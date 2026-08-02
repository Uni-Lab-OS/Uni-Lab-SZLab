#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_python="${UNILAB_PYTHON:-python}"
dist_dir="${UNILAB_PACKAGE_DIST_DIR:-${repo_root}/dist}"

mkdir -p "${dist_dir}"
exec "${unilab_python}" -m unilabos.app.main package build \
  --path "${repo_root}" \
  --out "${dist_dir}"
