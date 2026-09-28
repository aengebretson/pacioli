# Historical SPX expiration-forecast study

`luca_research.forecast_study` compares the existing rolling, EWMA, and
GARCH(1,1) expiry-variance forecasts across a bounded set of historical SPX
cutoffs. It is offline numerical research. It does not retrieve calendars or
market data, fit an option surface, calculate implied variance or VRP, price an
option, create a trade signal, or submit an order.

All 2023–2025 history supplied for this increment had already been inspected.
The result must therefore remain labelled **exploratory retrospective
research**, including its holdout-shaped 2025 partition. It is not untouched
performance evidence.

## Frozen design

The v1 study predeclares:

- 36 monthly origins, below the hard cap of 60, from January 2023 through
  December 2025;
- the first stored cash-session close of each month as the information cutoff;
- the stored SPXW PM rule-candidate expiration nearest cutoff plus 30 calendar
  days, choosing the earlier date on a tie;
- origin-year partitions named `exploratory_development_2023`,
  `exploratory_comparison_2024`, and
  `exploratory_retrospective_holdout_2025`;
- exactly 252 trailing close-to-close decimal log returns, zero mean, for every
  model at every origin;
- EWMA decay 0.94, normal GARCH(1,1), 500 optimizer iterations, tolerance
  `1e-8`, and one fit at the information cutoff; and
- the existing rolling model as the declared baseline, with EWMA and GARCH as
  challengers. Outcomes do not select or refit a model.

The first phase uses only calendar data, source identities, and dates; it does
not parse close fields or calculate scores. It writes
`forecast-study-predeclaration.json` before the second phase reloads the CSV and
parses close values. Each origin in the result then preserves two distinct
partitions:

1. 253 closes ending at the cutoff, which produce the shared 252-return fit
   vector; and
2. future closes strictly after the cutoff through the PM expiration, which
   are not supplied to any estimator.

The fit and outcome partitions retain their observations, upstream source IDs,
row hashes, and separate content hashes. Every model forecast also retains the
same eligible-history hash, schedule, parameters, convergence details, and
complete `h=1..H` conditional-variance vector from
`luca_research.expiry_forecast`.

## Horizon and scores

The primary forecast is cumulative physical variance in squared decimal log
return units:

```text
forecast = sum(h(1), ..., h(H))
realized = sum((log(close[t]) - log(close[t-1])) ** 2, t=1..H)
```

Both terms use the identical calendar-derived daily endpoints. Annualized
variance and volatility are reported for display, but scoring uses cumulative
horizon variance so neither operand is silently converted to a different
horizon or unit.

For each completed model, the study saves:

```text
QLIKE = log(forecast) + realized / forecast
signed variance error = forecast - realized
absolute variance error = abs(forecast - realized)
squared variance error = (forecast - realized) ** 2
```

QLIKE and variance errors are descriptive losses. Aggregate VRP, implied
variance, surface-relative richness, and research fair-value assumptions are
not synonyms for these quantities and are not calculated here.

An origin enters the common-origin table only if all three models completed and
were scored. Individual all-available metrics are reported separately. A
failed model is never replaced or relabelled; the per-origin forecast failure,
optimizer details, and comparison exclusion remain in the full result.

The predeclared GARCH boundary diagnostic flags omega at or below `1e-12`,
alpha or beta at or below `1e-8`, or persistence `alpha + beta` within `1e-6`
of one. These thresholds are diagnostics, not reasons to tune or discard a fit
after seeing its loss.

Monthly horizons can share daily returns. The plan identifies every overlapping
origin pair and its shared endpoint count. Results report no naive standard
errors, p-values, or significance claims because the losses are dependent.

## Run against supplied reference inputs

Install the exact existing numerical dependency set if it is not already
available. No dependency changes are required:

```bash
python3 -m venv /tmp/luca-forecast-study-venv
/tmp/luca-forecast-study-venv/bin/python -m pip install -r research/requirements.lock
/tmp/luca-forecast-study-venv/bin/python -m pip install --no-deps --no-build-isolation -e research
```

Then run the numerical study from the repository root. The example requires an
explicit extraction-availability timestamp; that timestamp is provenance for
the supplied reconstruction, not proof that each historical observation was
available at that exact market cutoff.

```bash
PYTHONPATH=research/src \
  /tmp/luca-forecast-study-venv/bin/python research/examples/forecast_study.py \
  --index /path/to/output/reference/daily/index.csv \
  --calendar /path/to/output/reference/spx-calendar.json \
  --input-available-at 2026-09-28T16:24:25Z \
  --output-dir /path/to/output/forecast-study
```

Keep the generated and licensed data in the coordinator output directory, not
in Git. The command emits:

- `forecast-study-predeclaration.json`: date-only plan, fixed rules, input,
  calendar, and exact source-code identities;
- `forecast-study-result.json`: every cutoff-only input, future outcome,
  full per-origin forecast, score, failure, common-origin comparison, and next
  design recommendation;
- `forecast-study-app.json`: `luca.spx-research-display.v1` `runs` records for
  the existing private viewer shape, plus the study comparison summary;
- `forecast-study-report.md`: compact human-readable methodology, results,
  diagnostics, overlap treatment, and limitations; and
- `forecast-study-output-manifest.json`: paths, byte counts, and SHA-256 hashes
  for the four research artifacts.

The code identity records the base Git commit and hashes of the exact study,
expiry, estimator, GARCH, and example source files. This matters for a worker
run because its implementation is not yet represented by the base commit.

## Interpretation and next design

The compact summary can identify the descriptively lowest common-origin mean
QLIKE model and quantify GARCH failures or boundary estimates. It cannot show
that a difference is statistically significant, economically tradeable, or
profitable after option pricing, spreads, execution, and futures hedging.

The next calibration/holdout increment should freeze any choice made from this
inspected study, use subsequently unavailable observations with versioned
publication-vintage evidence, and qualify actual historical SPXW listings.
Before inference it should also predeclare either non-overlapping expirations or
a dependence-aware procedure. This initial sample must not be silently retuned
to improve its reported ranking.

## Calendar and data limitations

- Calendar rows are PM eligibility rule candidates, not evidence that a
  particular contract or strike was listed at an origin.
- The XNYS cash-session snapshot is not the Cboe extended session and is not a
  historical announcement-vintage database.
- Source extraction time does not verify historical vendor publication time or
  later corrections.
- Daily index closes cannot establish quote freshness, option prints, event-time
  joins, executable theoretical values, or futures-hedged P&L.
- The study is analytical binary-floating-point research, not authoritative
  ledger arithmetic.

Software test suites remain separate from this bounded numerical run.
