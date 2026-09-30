# Chronological curve-premium research

Q2-T18 / Q2-I18. Offline, unintegrated research only. No production imports,
network access, raw-data copies, orders or UI changes. This folder is the sole
source change. Generated inputs/results belong in an external `output/` directory.

`predeclare.py` defines a fixed exploratory specification; it is not tuned after
scoring. `inventory.py` streams the supplied option/replay files.
`benchmark.py forecast` reuses the assigned baseline's rolling/EWMA/GARCH code,
saves each forecast and earlier fit partition, and seals files before
`benchmark.py score` computes realized outcomes. `contracts.py` is a separate,
strict ATM-IV proxy interface and future dollar comparison interface. No ATM
history is accepted automatically from the daily option export. `schemas.json`
contains versioned JSON Schema definitions and field contracts.

## Reproduction

Run from this worktree root. Supply a **new** external directory named `output`
for reproduction; the forecast and outcome files refuse overwriting. The
original predeclaration and sealed forecast files must be preserved.

The supplied venv's launcher resolves to Python 3.12 on this host, while its
packages have Python 3.11 ABIs. The command below uses an already installed
Python 3.11 interpreter and the **read-only pinned package directory**. It does
not install packages, edit the venv, or trust an editable-package pointer to
another checkout. `benchmark.py` prepends this worktree's `research/src`.

```bash
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONPATH=/home/andrew/luca-development/state/runs/Q2-T14-20260928171645-eee620/output/research-venv/lib/python3.11/site-packages
research_python=/home/andrew/.local/bin/python3.11
research_reference=/home/andrew/luca-development/state/maintenance/spx-trading-next-20260928/reference
research_output=/absolute/path/to/new/output
mkdir -p "$research_output"
timeout 10 "$research_python" -B research/curve_premium/prepare.py --output "$research_output"
timeout 180 "$research_python" -B research/curve_premium/inventory.py \
  --reference "$research_reference" \
  --options /home/andrew/luca-development/state/maintenance/spx-trading-next-20260928/event-reference/daily-quotes.csv \
  --replay /home/andrew/vol-term-structure/data/replay-workers-20260929/qualify-session \
  --output "$research_output"
timeout 1500 "$research_python" -B research/curve_premium/benchmark.py forecast \
  --reference "$research_reference" --output "$research_output"
timeout 180 "$research_python" -B research/curve_premium/benchmark.py score \
  --reference "$research_reference" --output "$research_output"
timeout 30 "$research_python" -B research/curve_premium/diagnostics.py --output "$research_output"
timeout 180 "$research_python" -B research/curve_premium/reconcile.py \
  --reference "$research_reference" --output "$research_output"
```

These are bounded numerical calculations and artifact reconciliation, **not
software tests**. No pytest/unittest/CTest, browser tests or CI were run.
Forecasts include run timestamps, so whole-file hashes differ on a reproduction;
numerical content is deterministic for identical inputs, code and environment.

## Statistical interpretation

All 2023–2025 data was previously inspected. Date ordering does not create an
untouched holdout. Future confirmation after 2026-09-30 remains unperformed.
For VIX strip proxies, `W_market=(index/100)^2*D/365` and physical `W_P` is summed
over exactly the same calendar span using future **session dates only** and
past-return model fits. Endpoints with no SPX close are excluded. VIX and SPX
intraday clocks, historical receipt times and calendar vintages are not verified;
the common 17:00 research cutoff is an assumption, not causal trading evidence.

Normal excess is the historical expectation of the measured discrepancy, not a
structurally identified risk premium. ATM IV-squared tenor is strike-dependent;
neither it nor a residual supplies exact option fair value. Model errors and
proxy mismatch remain embedded. Intervals are empirical forecast-error bands,
with uncertainty exclusions explicitly attached. Overlapping outcomes are
never treated as independent; non-overlapping schedules are common to model
candidates, and HAC estimates are descriptive asymptotic uncertainty, not model
superiority evidence. Long-term primary samples are particularly small.

Current Cboe [term-index methodology](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_SPX_Target_Expected_Volatility_Term_Indices.pdf)
was consulted for the strip distinction and 9/30/93/184/366-day targets. It is not
verification of historical methodology versions.
