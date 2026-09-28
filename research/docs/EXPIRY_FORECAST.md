# Expiration-aligned physical-variance forecast

`luca_research.expiry_forecast` extends the Q1 rolling, EWMA and GARCH(1,1)
estimators to one explicit option interval. It is an offline research component,
not an option pricer, exchange calendar, volatility-risk-premium calculation or
authoritative accounting calculation.

Import it without changing the package-level exports:

```python
from luca_research.expiry_forecast import run_expiry_forecast

artifact = run_expiry_forecast(request_document, normalized_close_document)
```

Both arguments are already-loaded mappings. The callable performs no file,
network, provider, calendar or database access. The close document uses the Q1
`luca.normalized-close.v1` contract and retains its validated input ID and
content SHA-256.

## Exact interval and information set

The caller supplies an information cutoff, actual expiration date, and the
strictly increasing daily-close endpoints in `(cutoff, expiration]`. The final
endpoint must equal expiration. This makes the number of forecast periods `H`
explicit and avoids converting a calendar interval into a hardcoded number of
sessions. Calendar ID, version and source are required provenance, and the
artifact fingerprints the supplied schedule.

Only `boundary_precision: daily_close` is supported. Date-time endpoints,
morning settlement, an intraday cutoff, or a fractional final session are
rejected. Those cases require qualified intraday or settlement data and a
separately reviewed interval convention; daily closes cannot supply that
precision.

All three models receive the same trailing decimal log-return vector ending at
the cutoff, the same `H`, and the same return-unit convention. A normalized
input may contain observations after the cutoff for a historical
reconstruction, but they are ignored during fitting. The output records the
eligible-history hash and count separately from the full input hash and warns
when post-cutoff observations were present.

The only refit policy in v1 is
`fit_once_at_information_cutoff`. Model selection is also fixed by the request:
the caller names `selected_model` and explains a predeclared `selection_basis`.
This module neither consumes expiration outcomes nor changes selection or
fitting settings based on them. The basis is retained as caller provenance, not
independently verified by this module. Every other model is labelled
`challenger`.

## Forecast and units

Rolling variance reuses `historical_variance`; EWMA reuses `ewma_variance` with
the declared decay and Q1 first-innovation-squared initialization. Their daily
conditional forecasts are flat after the cutoff. GARCH delegates both fitting
and its analytical multi-step forecast to `fit_garch11`, which is the existing
pinned `arch` integration. GARCH estimation is not reimplemented here.

For every model, period `h` is reported with its explicit start and end date in
decimal-return-squared units. Physical cumulative variance is

```text
W_P = h(1) + h(2) + ... + h(H).
```

In particular, the GARCH result is the sum of the complete `arch` forecast
vector. It is not `h(H)`, and it is not current variance multiplied by `H`.

For cutoff date `t`, expiration date `T`, and configured calendar annualizer
`D`, the artifact also reports

```text
calendar_year_fraction = (T - t).days / D
annualized_variance = W_P / calendar_year_fraction
annualized_volatility = sqrt(annualized_variance).
```

`W_P` remains the primary horizon variance. No implied variance `W_Q`, VRP,
surface-relative richness or option fair value is calculated. A downstream VRP
consumer must compare `W_P` and `W_Q` over this same interval and use the agreed
sign `W_Q - W_P`; it must label that separately from surface-relative or pricing
assumptions.

## Request contract

The v1 request has this shape (values are illustrative):

```json
{
  "schema_version": "luca.expiry-variance-request.v1",
  "run_id": "illustrative-expiry-forecast-v1",
  "research_use": "illustrative_fixture",
  "input": {
    "input_id": "synthetic-spx-like-v1",
    "sha256": "<validated normalized-close SHA-256>",
    "available_at": "2024-09-03T21:00:00Z"
  },
  "interval": {
    "cutoff": "2024-07-16",
    "expiration": "2024-08-14",
    "interval_end_dates": ["2024-07-17", "...", "2024-08-14"],
    "boundary_precision": "daily_close",
    "calendar": {
      "calendar_id": "illustrative-weekday-schedule",
      "version": "fixture-v1",
      "source": "illustrative fixture dates; not exchange-certified"
    }
  },
  "model": {
    "fitting_window_returns": 90,
    "minimum_fit_returns": 60,
    "mean": "zero",
    "ewma_decay": 0.94,
    "calendar_days_per_year": 365.2425,
    "garch_max_iterations": 500,
    "optimizer_tolerance": 1e-08,
    "refit_policy": "fit_once_at_information_cutoff",
    "selected_model": "garch_1_1",
    "selection_basis": "predeclared illustration; not selected from this expiration outcome"
  }
}
```

`research_use` must explicitly be `illustrative_fixture`,
`exploratory_historical`, or `unexamined_evaluation`. This label prevents an
illustrative or previously inspected calculation from being presented as new
held-out evidence.

## Result and failure behavior

`luca.expiry-variance-result.v1` contains:

- request, input, eligible-history, model and schedule identities;
- the cutoff, expiration, period count, units and annualization convention;
- the declared fit window, EWMA decay and fixed-at-cutoff refit policy;
- every model's parameters, fit metadata, convergence state, `h(1)..h(H)`,
  `W_P`, annualized variance and volatility;
- selected/challenger roles, warnings, and structured exclusions.

A failed GARCH optimizer produces an excluded `garch_1_1` result with its
available convergence detail and `fallback_used: false`. Challenger failure
makes the artifact `partial`; failure of the selected model makes it `failed`
even when a challenger completed. No baseline is silently relabelled as GARCH.
Contract failures also return a structured failed artifact.

## Bounded illustrative calculation

With the pinned research environment installed, run from the repository root:

```bash
PYTHONPATH=research/src \
  python research/examples/expiry_forecast.py \
  --output /tmp/luca-expiry-forecast.json
```

The example uses the committed synthetic Q1 fixture, not observed SPX or
unexamined evaluation data. It declares a 29-calendar-day, 21-daily-interval
schedule and writes one result artifact. It independently recomputes each
completed model's period sum and annualization identities and reports their
absolute differences to stderr. The demonstration does not run a software test
suite, fit from expiration outcomes, calculate VRP or establish profitability.
