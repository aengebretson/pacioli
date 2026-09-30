# Q2-T19 structural calibration research

This is an isolated offline diagnostic module against Q2-T14 base
`9e37f09030037b6618afdc4dccd9c8a6638843a7`. It does not modify or integrate the
baseline and is not an accepted pricer, forecasting service, or trading signal.
All results and the frozen predeclaration live in the assigned runtime output.
No market data belongs in this source directory.

## Reproduce

From the assigned worktree, with the original local inputs available:

```bash
bash research/curve_structural/run.sh
bash research/curve_structural/diagnose.sh
```

The first command completes the saved-parameter reproduction, two staged
calibrations, numerical sensitivities, and streamed input inventory. The second
adds feasibility-bound identification and narrow deterministic/Monte Carlo
checks of concerns found in the first calculation; it does not calibrate.
Each command has a 1,800-second timeout and a 30-second TERM-to-KILL grace.
The research session has a separate three-hour assignment budget. There is no
automatic retry or relaunch. `run.sh` accepts `--output-dir` only under the
assigned runtime `output/`; `diagnose.sh` uses the primary output directory.

The original environment was built with CPython 3.11. Its `bin/python` symlink
now resolves to host Python 3.12. The wrappers use the already-existing
`/home/andrew/.local/bin/python3.11` and read NumPy/SciPy from the original
read-only environment via `PYTHONPATH`. They disable bytecode and set numerical
threads to one. No install or environment repair is performed. Paths are
explicitly pinned to this assignment. Missing dependencies/inputs are errors.

`predeclaration.json` must already exist in the primary runtime output. It was
written before new historical outcome scoring; its SHA-256 is recorded in the
results. Reproduction does not redefine dates, weights, or models from results.

## Specifications

Physical coefficients and lambda1 remain fixed at the saved 2019–2022 fit.
All return states use the same frozen particle filter through the origin only,
starting at 2019-12-02, with 512 particles and seed 29. No later observation
enters a state. The original filter's random offsets depend on prefix length;
prefixes are calculated separately to reproduce its numerical convention.

* `saved_jan2024`: the January 3 lambda2, frozen on subsequent evaluation dates.
  Its 2023 scores are retrospective diagnostics, not causal train forecasts.
* `pooled_return_state`: one pQ across 12 2023 month ends; equal squared
  VIX-point residuals over five tenors; P-filtered mean states fixed.
* `pooled_vix_anchor`: one pQ over the same dates; the affine 21-period relation
  is inverted for h using observed VIX. Fit the four remaining tenors with
  equal weights. Reject nonpositive states without clipping. This is a
  deliberately simple observation-conditioned diagnostic, not the paper's
  full joint likelihood and not a forecast of its VIX anchor.

Both candidates use 10,001 grid points, at most 150 scalar-refinement
iterations, and the nonnegative gamma2Q branch. The objective identifies pQ,
not the sign of gamma2Q. A fixed intercept links pQ to long-run variance.
The anchor model has a training-derived state-positivity boundary strictly
inside the outer stationarity interval. The additional diagnostics explicitly
report this boundary; optimizer success alone is not identification evidence.

Evaluation uses eight fixed 2024–2025 quarterly-spaced month ends. All history
was previously inspected and remains exploratory. Main comparable metrics are
four unanchored-tenor RMSE and VIX9D RMSE. Five-tenor and two-near-tenor
metrics that include the exactly fitted VIX anchor are labelled separately.
No option-price target or future realized variance is fitted or scored.

## Numerical methods

`numerics.py` derives the k=1 Q affine transform by integrating the implemented
two-Gaussian transition. It uses finite-cutoff Fourier inversion for a
simulation-independent price, checks against one-period Black, Gaussian
quadrature and the unchanged baseline Monte Carlo. The put from Fourier
pricing is obtained by parity and is not an independent parity validation.
The unchanged shared-path simulation provides separate payoff/parity and
martingale diagnostics with adjacent antithetic-pair standard errors.

The research scripts cap simulations at 80,000 paths. Intervals in inherited
Monte Carlo structures retain the field `confidence_interval_95` and describe
conditional simulation error only. State quantiles, local coefficient changes,
calendar mappings and hypothetical carry changes are sensitivity scenarios,
not parameter intervals or total fair-value confidence intervals.

Fractional model periods are explicitly analytic continuations of an affine
expectation, not a new pathwise fractional-time GARCSH process. Retrospective
session counts inferred from close dates do not establish a certified calendar.

## Artifacts and schema

Primary artifacts:

* `structural-validation.json`: `luca.curve-structural.validation.v1`, embeds
  baseline, chronological comparison and numerical sections; explicitly lists
  missing validation and integration status.
* `predeclaration.json`: `luca.curve-structural.predeclaration.v1`, dates,
  objectives, seeds, numerical bounds, information cutoffs and exclusions.
* `provenance.json`: `luca.curve-structural.provenance.v1`, exact input hashes,
  source hashes, base/branch, environment, commands and elapsed times.
* `structural-validation-report.md`: interpretation, measured failures and
  primary-source audit, with acceptable uses and next action.

Supporting JSONs preserve per-date observed/predicted curves, signed
observed-minus-model residuals, state identities and fit checkpoints. Input
inventory streams the 358 MB option file and hashes the 374 MB replay file;
it does not load either large file into memory or score execution outcomes.
No licensed input is copied into tracked source or uploaded.

`source-audit.json`, `artifact-reconciliation.json`, `HANDOFF.md`,
`CHANGED_FILES.txt`, and exact-schema `handoff.json` complete the review record.
The report and handoff are reviewed narrative artifacts; numerical entrypoints
do not regenerate them automatically. They must be reconciled after any rerun.
No pytest, unittest, CTest, browser, CI or other automated software tests are
part of these commands.
