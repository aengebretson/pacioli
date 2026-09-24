#!/usr/bin/env bash
set -euo pipefail

research_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verification_root="$(mktemp -d "${TMPDIR:-/tmp}/luca-research-verify.XXXXXX")"
trap 'rm -rf -- "$verification_root"' EXIT

python3 -m venv "$verification_root/venv"
verification_python="$verification_root/venv/bin/python"

PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 \
  "$verification_python" -m pip install --upgrade pip==26.0.1
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 \
  "$verification_python" -m pip install -r "$research_root/requirements.lock"
PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 \
  "$verification_python" -m pip install \
  --no-deps --no-build-isolation -e "$research_root"

"$verification_python" "$research_root/verify.py" "$@"
