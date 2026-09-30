#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
RUNTIME=/home/andrew/luca-development/state/maintenance/vol-curve-20260930/structural
PINNED=/home/andrew/luca-development/state/runs/Q2-T14-20260928171645-eee620/output/research-venv
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/research/src:$PINNED/lib/python3.11/site-packages"
export TMPDIR="$RUNTIME/output"
exec timeout --signal=TERM --kill-after=30s 1800s /home/andrew/.local/bin/python3.11 -B "$ROOT/research/curve_structural/diagnose.py"
