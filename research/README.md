# LUCA optional volatility research package

`luca-research` is a standalone, offline Python package for the first volatility
demo. It computes historical-variance and EWMA baselines and delegates
GARCH(1,1) maximum-likelihood fitting and analytical forecasting to the
maintained `arch` library. It is analytical software: its binary floating-point
results are not authoritative LUCA ledger values.

The package performs no data acquisition and has no platform, provider,
database, network, option-pricing, HAR, live-scoring, or backtesting behavior.
The fixture is synthetic and resembles an index level only in scale.

## Install and run offline

From the repository root, create an isolated environment and install the exact
pinned package set:

```bash
python3 -m venv /tmp/luca-research-venv
/tmp/luca-research-venv/bin/python -m pip install --upgrade pip==26.0.1
/tmp/luca-research-venv/bin/python -m pip install -r research/requirements.lock
/tmp/luca-research-venv/bin/python -m pip install --no-deps --no-build-isolation -e research
```

Run the synthetic approximately-30-calendar-day example:

```bash
/tmp/luca-research-venv/bin/luca-volatility \
  --request research/fixtures/synthetic_request.json \
  --input research/fixtures/synthetic_spx_like.json \
  --output /tmp/luca-volatility-result.json
```

The CLI exits 0 for a complete artifact, 3 for a partial artifact, and 2 for a
failed artifact. Expected validation errors and optimizer failures are emitted
as structured JSON; GARCH failures never cause substitution of a baseline.

The equivalent callable API is:

```python
from luca_research import run_analysis

artifact = run_analysis(request_document, normalized_close_document)
```

Both arguments are ordinary mappings already loaded by the host. The function
does no I/O and returns the same JSON-compatible artifact as the CLI. Before
decoding JSON, the CLI limits the serialized request to 256 KiB and the
serialized close input to 2 MiB. Callable hosts are responsible for applying an
equivalent transport/read bound before constructing their mappings; validation
cannot recover allocation or parsing work already performed by a caller.

## Stable generic contract

`luca.normalized-close.v1` requires an input ID, an explicit close unit, and
strictly increasing `{date, close}` observations. Dates are canonical ISO
calendar dates. Closes must be finite and positive. The content SHA-256 is over
the validated canonical document, and the request must name both the input ID
and that hash. Duplicate or unordered dates, ambiguous units, and nonfinite or
nonpositive closes are rejected. JSON numbers that cannot be represented as a
finite binary64 value are also rejected with a structured diagnostic.

`luca.volatility-request.v1` provides:

- an analysis ID and expected input identity/hash;
- fit, selection, and held-out boundaries;
- unique evaluation origins with explicit endpoints and split labels;
- lookback, minimum fit coverage, zero/constant mean convention, EWMA decay,
  shared calendar-day annualizer, optimizer tolerance/iteration budget, and a
  recorded seed; and
- caller-selected observation/origin limits below hard package caps of 10,000
  observations, 100 origins, and 2,000 GARCH optimizer iterations per origin.

Arrays exceeding the selected observation or origin limit are rejected from
their length before any member is read or converted. Arrays exactly at the
limit still receive complete member validation.

Selection labels must lie entirely inside the selection range. Held-out labels
must lie entirely inside the held-out range, and the ranges cannot touch or
overlap. At each origin, fitting uses only returns whose ending close is at or
before that origin. A window is eligible only if every model succeeds; all
metric tables therefore use the same origins.

`luca.volatility-result.v1` records the request and full input hashes, a hash of
the exact available input prefix fitted at each origin, dependency and code
versions, units, availability cutoff, actual fit range/count, horizon,
parameters, convergence/optimizer state, exclusions, errors, fitting failures,
per-origin losses, and descriptive aggregate metrics. No generated timestamp or
host/job ID is included, so repeated CLI and API runs can agree exactly.
Artifacts declare an absolute tolerance of `1e-12` and relative tolerance of
`1e-10` for comparison across otherwise compatible hosted and standalone
numerical runtimes; identity, date, status, and diagnostic fields compare
exactly. The tested CLI and callable API in one pinned environment agree as
exact JSON.

## Statistical and unit conventions

Close-to-close returns are decimal log returns, calculated as the difference of
the two log closes rather than the log of a precomputed ratio so an otherwise
valid extreme close pair cannot overflow or underflow during division. For
`mean: zero`, historical variance is mean squared return (`ddof=0`). With a
constant mean, the fitted sample mean is removed and sample variance uses
`ddof=1`. EWMA initializes from the first fitted innovation squared and applies
`v[t] = decay*v[t-1] + (1-decay)*innovation[t]^2`; its multi-step baseline is
flat at the origin variance.

The GARCH adapter fits normal GARCH(1,1) with either `Zero` or `Constant` mean in
`arch`. Decimal returns are multiplied by 100 only while fitting for numerical
conditioning. Omega and conditional variance are divided by 10,000 (and mu by
100) on return. Both upstream percent-unit parameters and converted parameters
are saved. Forecasting is the upstream analytical conditional-residual-variance
forecast; no custom optimizer is present. The request seed is recorded for a
portable host contract, but this fitted analytical code path makes no random
draws.

For an explicit `(origin, endpoint]`, every supplied close interval is
forecast, the conditional variances are summed, and only then is the cumulative
variance annualized by `calendar_days_per_year / (endpoint-origin).days`. The
realized proxy is the sum of squared close-to-close log returns over exactly the
same intervals with exactly the same annualizer. A 29- or 30-calendar-day target
is never converted to a hardcoded 21-session target.

QLIKE is `log(forecast) + realized/forecast`; squared variance error is
`(forecast-realized)^2`, using annualized variance for both operands. These are
descriptive losses, not an improvement threshold or model-acceptance gate.
Horizon labels can share returns when windows overlap, so
their losses are dependent. The artifact identifies overlapping pairs and this
slice does not calculate naive standard errors, p-values, or significance.

## Dependency and license choices

Runtime and build dependencies are exact pins in `requirements.lock` and
`pyproject.toml`. The direct numerical stack is NumPy 2.4.6 (BSD-3-Clause and
bundled compatible notices), SciPy 1.17.1 (BSD-3-Clause), pandas 3.0.6
(BSD-3-Clause), statsmodels 0.15.0 (BSD-3-Clause), and arch 8.0.0 (NCSA).
`arch` is the established maintained GARCH implementation; NumPy/SciPy provide
its numerical substrate, while pandas/statsmodels are required by that upstream
package. All are permissively licensed and remain optional to the Apache-2.0
LUCA C++ build. The lock also records the complete tested transitive set for
CPython 3.11. Versions are recorded in every result artifact.

The pins select the maintained `arch` 8.0.0 line and the newest releases that
were resolved and tested together on the repository's CPython 3.11 runtime.
This intentionally uses the Python-3.11-compatible NumPy/SciPy lines rather than
newer releases whose package metadata requires Python 3.12. Version upgrades
are explicit reproducibility changes and must rerun the upstream-parity tests.

No package is published by this repository task. To run tests after the install
above:

```bash
cd research
/tmp/luca-research-venv/bin/python -m unittest discover -s tests -v
```

## Unattended verification

From the repository root, the following command creates a disposable virtual
environment, installs only the exact committed pins, runs `pip check` and all
research tests, compares the synthetic callable and CLI artifacts exactly, and
reports their measured wall time against a 30-second verification budget:

```bash
bash research/verify-isolated.sh
```

The command needs CPython 3.11 or another supported interpreter with `venv`,
plus package-index access while creating the disposable environment. The
installed CLI and callable API themselves remain offline and require neither a
browser login nor platform, provider, database, or network access. The verifier
exits nonzero for a missing/mismatched pin, a broken dependency, any test
failure, differing CLI/API artifacts, a non-complete synthetic result, or a
runtime-budget breach. Use `--max-synthetic-seconds` only to state a different
machine-specific verification budget explicitly.
