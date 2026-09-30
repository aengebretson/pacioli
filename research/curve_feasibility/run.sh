#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 BLIS_NUM_THREADS=1
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
research_python=/home/andrew/luca-development/state/runs/Q2-T14-20260928171645-eee620/output/research-venv/bin/python
research_output=${1:?Pass the assigned external output directory}
# Declare before scoring; never overwrite a prior receipt.
"$research_python" -B - "$source_dir" "$research_output" <<'PYCODE'
import datetime, hashlib, json, pathlib, sys
src, out = map(pathlib.Path, sys.argv[1:])
if 'worktrees' in out.resolve().parts:
    raise SystemExit('Generated artifacts must be outside Git worktrees')
out.mkdir(parents=True, exist_ok=True)
p = out / 'predeclaration.json'
r = out / 'predeclaration-receipt.json'
if not p.exists() and not r.exists():
    b = (src / 'predeclare.json').read_bytes()
    p.write_bytes(b)
    r.write_text(json.dumps({'declared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'sha256': hashlib.sha256(b).hexdigest(), 'scoring_started': False}, indent=2)+'\n')
PYCODE
timeout --signal=TERM --kill-after=10s 300 "$research_python" -B "$source_dir/audit.py" --input /home/andrew/vol-term-structure/data/replay-workers-20260929/qualify-session --output "$research_output"
timeout --signal=TERM --kill-after=10s 120 "$research_python" -B "$source_dir/inventory.py" "$research_output"
timeout --signal=TERM --kill-after=10s 60 "$research_python" -B "$source_dir/report.py" "$research_output"
