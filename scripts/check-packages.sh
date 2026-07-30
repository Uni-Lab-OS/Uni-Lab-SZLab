#!/usr/bin/env bash
set -euo pipefail

script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${script_root}/check-szlab-package.sh"
"${script_root}/check-ai4c-package.sh"
