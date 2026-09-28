# Direct two-shock HN-GARCSH research candidate

This note documents `luca_research.vrp`, model version
`hn-garcsh-direct-v1`. It is an isolated research candidate. It does not
replace the historical, EWMA, or ordinary GARCH baselines, classify VIX
regimes, submit orders, or turn an arbitrary volatility multiplier into a
structural variance-risk premium.

## Primary source and source boundary

The implemented equations are from Marcos Escobar-Anel, Lars Stentoft, and
Xize Ye, “The Role of Variance Risk Premium in Derivative Pricing: Modeling,
Estimation and Impact,” *Journal of Futures Markets* (2026),
[DOI 10.1002/fut.70132](https://onlinelibrary.wiley.com/doi/10.1002/fut.70132).
The article is the primary source for Equations (1), (3), (5)–(13), (19)–(20),
and (30)–(32) below. It refers to the authors’ foundational preprint, “Setting
the VIX Free: A Generalized Affine GARCH Model,” SSRN 4664927, for further
model details.

Two exact source components remain unresolved:

- The accessible 2026 article says that the transformation follows a pricing
  kernel with separate risk preferences `lambda1` and `lambda2`, but it does
  not print the pricing-kernel equation. The foundational preprint’s full text
  was not publicly retrievable in this task environment. The package therefore
  does not invent or expose a pricing-kernel function.
- The accessible article defines physical and risk-neutral persistence and
  long-run means, but it does not state a complete admissibility theorem. The
  package’s constraints are identified below as sufficient implementation
  constraints, not quoted as a theorem from the paper.

Those gaps do not prevent implementation of the explicitly published P and Q
dynamics, conditional variance expectations, VIX term structure, or
horizon-matched cumulative variance. They do prevent claiming a paper-exact
pricing kernel or a complete option-pricing implementation.

## Published dynamics and conventions

All variances are per-trading-day decimal log-return variances. The risk-free
rate `r` is the continuously compounded rate for one model period. Under the
physical measure P, Equation (1) is

```text
log(S_t) = log(S_{t-1}) + r + lambda1 h_t + sqrt(h_t) z_{1,t},
```

where `z_1` is iid standard normal under P. Thus the physical conditional log
return mean is `r + lambda1*h_t`; it is not a separately fitted constant-mean
convention.

The physical HN-GARCSH variance recursion in Equation (5) is

```text
h_t = omega + beta h_{t-1}
      + alpha (z_{1,t-1} - gamma1 sqrt(h_{t-1}))^2
      + (rho/k) sum_i=1^k
          (epsilon_{i,t-1} - gamma2 sqrt(h_{t-1}))^2.
```

The `epsilon_i` are iid standard normal and independent of `z_1`. `k=1` is
the literal two-Gaussian-shock instance implemented in the example: one return
shock and one independent variance shock. The API retains the paper’s integer
`k` generalization, where the auxiliary sum can be viewed as non-central
chi-squared.

Under Q, Equation (3) changes the conditional log-return mean to the martingale
correction:

```text
log(S_t) = log(S_{t-1}) + r - h_t/2 + sqrt(h_t) z*_{1,t}.
```

Equations (6) and the text immediately following it retain the variance form
and explicitly transform the leverage parameters:

```text
gamma1* = gamma1 + lambda1 + 1/2
gamma2* = gamma2 + lambda2

h_t = omega + beta h_{t-1}
      + alpha (z*_{1,t-1} - gamma1* sqrt(h_{t-1}))^2
      + (rho/k) sum_i=1^k
          (epsilon*_{i,t-1} - gamma2* sqrt(h_{t-1}))^2.
```

`lambda1` is fixed by the caller in this increment. It is both the physical
conditional-return premium coefficient in Equation (1) and part of the
published Q transformation. `lambda2` is a distinct, constant price of the
independent variance shock and is the only calibrated parameter here. The
physical structure and filtered state are never relabelled as pricing
parameters.

## Conditional expectations and sufficient constraints

Equations (7)–(12) give

```text
c   = omega + alpha + rho
p   = beta + alpha gamma1^2  + rho gamma2^2
p*  = beta + alpha gamma1*^2 + rho gamma2*^2

E^P[h_next | h] = c + p h
E^Q[h_next | h] = c + p* h

mu  = c / (1 - p)
mu* = c / (1 - p*).
```

The implementation applies these sufficient numerical constraints:

- `omega >= 0`, `beta >= 0`, `alpha > 0`, `rho > 0`, and integer `k >= 1`;
- positive filtered variance state;
- `p < 1`; and
- `p* < 1`, with a `1e-10` stationarity margin during calibration.

The nonnegative recursion coefficients make the pathwise variance
nonnegative; a strictly positive state is required wherever a square root or
VIX is calculated. `p,p* < 1` makes the long-run means above finite. These are
deliberately described as sufficient implementation restrictions because the
primary article does not print a complete admissibility result.

## Horizon-matched cumulative variance and sign

The caller supplies filtered `h_next = h_{t+1}` at a declared information
cutoff. For a horizon of `H` trading-day intervals, the package reports the
full expected paths and

```text
W_P = sum_{n=1}^H E_t^P[h_{t+n}]
W_Q = sum_{n=1}^H E_t^Q[h_{t+n}]
VRP = W_Q - W_P.
```

Both sides use the same state, horizon, and decimal-return-squared units. This
LUCA sign convention is intentionally the opposite of the paper’s one-step
`P - Q` definition in Equation (13). The artifact records both conventions.
Annualized volatility is `sqrt(W / (H/252))`; annualization happens only after
the interval variances are summed.

The model operates in trading-day intervals because the paper’s VIX equations
use 252 trading days per year. Mapping an option’s exact calendar expiration
and settlement timestamp to these intervals requires an upstream exchange
calendar. The package does not silently equate every 30-calendar-day interval
with 21 observations.

## VIX term-structure objective

Equations (19)–(20) define the observed daily expected variance and the model
term value:

```text
Hbar_market(tau) = (VIX_market(tau)/100)^2 / 252

Hbar_model(tau) = (1/tau) sum_{n=1}^tau E_t^Q[h_{t+n}]
VIX_model(tau)  = 100 sqrt(252 Hbar_model(tau)).
```

For numerical stability the implementation calculates the affine expectation
path recursively. This is algebraically the same quantity as the closed form
in Equation (20), including `h_{t+1}` as the first interval.

Equation (30) scales each term error as

```text
xi(tau) = (VIX_market(tau) - VIX_model(tau)) / (100 sqrt(252)).
```

The bounded entry point minimizes `sum(weight(tau) * xi(tau)^2)`. A caller may
provide fixed inverse residual-variance weights, which corresponds to the
parameter-dependent squared-error part of Equation (31). This small
cross-sectional calibration does **not** claim the complete joint likelihood
in Equation (32): it neither estimates residual variances nor adds a return
likelihood.

The entry point is intentionally bounded to 32 unique maturities, 2,000 model
periods per maturity, and at most 2,000 optimizer evaluations. Bounds are
intersected with the `p*` stationarity region. Bounds crossing
`lambda2 = -gamma2` are rejected because the VIX term structure depends on
`(gamma2 + lambda2)^2`; the caller must select one identification branch.

Even with multiple maturities, this objective identifies `p*`, not the sign of
`gamma2 + lambda2`. The artifact reports the symmetric value
`-2*gamma2 - lambda2`, which produces the same VIX term structure when it is
otherwise admissible. A good numerical fit is not proof that `lambda2` is
economically identified.

## API and artifact contract

The public API is imported from `luca_research.vrp`:

```python
from luca_research.vrp import (
    ArtifactMetadata,
    CalibrationConfig,
    PhysicalDynamics,
    VixTermObservation,
    build_calibration_artifact,
    calibrate_vix_term_structure,
)
```

`calibrate_vix_term_structure(...)` takes fixed physical dynamics, fixed
`lambda1`, fixed filtered `h_next`, same-cutoff VIX term observations, an
explicit report horizon, and optimizer bounds. It returns convergence details,
the objective, all term residuals, transformed Q dynamics, `W_P`, `W_Q`, and
`W_Q-W_P`.

`build_calibration_artifact(...)` produces
`luca.direct-vrp-result.v1`. Required metadata includes run and dataset
identity, content SHA-256, dataset classification, input cutoff, availability
time, state as-of time, and state availability time. The artifact contains no
generated timestamp, empirical claim, or silent data fallback.

The nested `luca.hn-garcsh-option-pricing-input.v1` contract carries the model
parameters and state to a later option pricer. It is explicitly marked
`ready_for_option_pricing: false` until the affine joint-MGF recursion and
inversion are implemented and checked against the exact primary source. It
also enumerates required contract identity, exact settlement/calendar
provenance, forward or spot timing, curve/carry inputs, Greeks, and warnings.
It prohibits a silent Black-price substitution or arbitrary volatility
multiplier. No option theoretical value is emitted by this increment.

## Demonstration and interpretation limits

`research/examples/direct_vrp.py` constructs labelled synthetic VIX terms from
the same equations, calibrates `lambda2` on a preselected branch, and prints a
JSON artifact. It does not read the supplied exploratory SPX archive because
that archive contains no qualified VIX term structure. Its fitted premium is
therefore a numerical identity check only—not an SPX estimate, an unexamined
evaluation, a trading signal, or evidence of profitability.

Remaining work before empirical or pricing use includes physical-parameter
estimation, an explicitly documented variance-state filter, qualified
same-cutoff VIX term observations, exact exchange-calendar horizon mapping,
the paper-exact pricing kernel, the affine joint MGF and option inversion,
parameter uncertainty, and genuinely held-out evaluation.
