#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_command="${UNILAB_COMMAND:-unilab}"
check_working_dir="${UNILAB_CHECK_WORKING_DIR:-$(mktemp -d)}"

export PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"

cd "${repo_root}"
set +e
check_output=$("${unilab_command}" \
  --check_mode \
  --devices "./szlab_poly_studio" \
  --external_devices_only \
  --working_dir "${check_working_dir}" 2>&1)
check_status=$?
set -e

printf '%s\n' "${check_output}"
if (( check_status != 0 )); then
  exit "${check_status}"
fi
if grep -Eq '\[ERROR\]|\[WARNING\]|[0-9]+ 个错误' <<<"${check_output}"; then
  echo "Uni-Lab registry verification reported errors." >&2
  exit 1
fi
