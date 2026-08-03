#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unilab_python="${UNILAB_PYTHON:-python}"
check_working_dir="${UNILAB_CHECK_WORKING_DIR:-$(mktemp -d)}"

export PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"

cd "${repo_root}"
"${unilab_python}" -m unilabos.app.main package inspect --path "${repo_root}"

set +e
check_output=$("${unilab_python}" -m unilabos.app.main \
  --check_mode \
  --workspace "${repo_root}" \
  --skip_env_check \
  --working_dir "${check_working_dir}" 2>&1)
check_status=$?
set -e

printf '%s\n' "${check_output}"
if (( check_status != 0 )); then
  exit "${check_status}"
fi
if grep -Eq '\[ERROR\]|[0-9]+ 个错误' <<<"${check_output}"; then
  echo "Uni-Lab registry verification reported errors." >&2
  exit 1
fi
