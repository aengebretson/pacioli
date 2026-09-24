# Portable volatility research boundary

The optional package in `research/` is the first bounded volatility-analysis
slice. It keeps floating-point research estimates separate from LUCA's exact
authoritative C++ ledger values and leaves the existing CMake graph unchanged.
Installing or importing the C++ library does not install Python, NumPy, SciPy,
pandas, statsmodels, or `arch`.

The portable boundary consists of two versioned input documents and one result
artifact:

```text
normalized closes + analysis request
                 │
                 ▼
       pure callable API (no I/O)
                 │
                 ▼
 historical / EWMA / arch GARCH forecasts
                 │
                 ▼
 versioned result with hashes, cutoffs, parameters,
 convergence, horizons, losses, exclusions and diagnostics
```

A hosted adapter can validate/load authorized data and pass the two mappings to
`luca_research.run_analysis`; the offline CLI only loads and writes JSON around
that same function. Neither route embeds vendor schemas or acquisition. This is
the stable generic Q2-facing boundary: `luca.normalized-close.v1`,
`luca.volatility-request.v1`, and `luca.volatility-result.v1`. A hosted job ID,
authorization decision, storage location, or generated timestamp belongs to the
host envelope, not the deterministic statistical result. Result configuration
declares `1e-12` absolute and `1e-10` relative cross-host numerical tolerances;
nonnumeric contract fields match exactly.

The close document requires explicit units and stable input identity. The
request binds its expected SHA-256, declares fit/selection/held-out boundaries,
and supplies unique origin/endpoint pairs. Result records state the exact
availability cutoff and fit range. A selection label cannot cross the held-out
boundary, and a held-out label cannot begin in selection. Future close values
are used only for the realized label after a forecast has been fit. Each fitted
record also hashes the precise observation prefix through its availability
cutoff, independently of the full evaluation-input hash.

Each model forecasts every actual close-to-close interval supplied in the
explicit `(origin, endpoint]` horizon. Interval conditional variances are summed
before a shared calendar-day annualization. The realized proxy sums squared log
returns across the same intervals. Consequently an approximately 30-calendar-
day endpoint is explicit and is not treated as an assumed 21-session horizon.

Historical, EWMA, and GARCH losses are evaluated only on origins where all three
models succeeded. Artifacts retain exclusions and upstream optimizer/convergence
details; GARCH failure is visible and never replaced. QLIKE and squared variance
error are descriptive, and no real-improvement threshold gates success.
Overlapping horizon labels reuse returns and are dependent, so the package flags
overlap and makes no naive significance claim.

Runtime is bounded by validated hard caps (10,000 observations, 100 origins,
2,000 optimizer iterations for each origin), with tighter values carried in
each request. This bounds the numerical work without adding network/process
control to the callable financial-analysis function.

See [`research/README.md`](../research/README.md) for schemas, formulas, exact
dependency/license pins, the callable API, the synthetic offline example, and
test commands. This increment does not include proprietary SPX observations,
option pricing, HAR/realized-variance inputs, live scoring, scheduling, rates
forecasting, generalized pipelines, or a universal backtesting/statistics
runtime.
