# Direct two-shock HN-GARCSH research model

`luca_research.vrp` is a bounded, offline research implementation of the
two-shock HN-GARCSH model. It estimates physical dynamics from daily index
returns, fits one pricing-risk parameter to an exact-date VIX term cross
section, reports horizon-aligned variance risk premium (VRP), and prices a
European call, put, and straddle by controlled simulation of the documented
risk-neutral dynamics. It does not submit orders, consume live data, or turn a
theoretical value into a trade score.

## Primary sources and source boundary

The dynamics and equation numbers below are from Marcos Escobar-Anel, Lars
Stentoft, and Xize Ye, “The Role of Variance Risk Premium in Derivative
Pricing: Modeling, Estimation and Impact,” *Journal of Futures Markets*
(2026), [DOI 10.1002/fut.70132](https://onlinelibrary.wiley.com/doi/10.1002/fut.70132).
The article cites the foundational preprint, “Setting the VIX Free: A
Generalized Affine GARCH Model,” SSRN 4664927.

The accessible article explicitly prints the P and Q return/variance dynamics,
the P-to-Q leverage transformation, conditional variance expectations, VIX
term calculation, and estimation objectives. It does not print the complete
pricing-kernel equation or a complete admissibility theorem. This package does
not invent either one. European pricing instead simulates the explicitly
published Q transition itself, which is sufficient to define the terminal
payoff distribution conditional on accepted Q parameters and state.

Cboe’s [Selected SPX Target Expected Volatility Term Indices
methodology](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_SPX_Target_Expected_Volatility_Term_Indices.pdf)
is the source for treating VIX9D, VIX, VIX3M, VIX6M, and VIX1Y as distinct
constant-maturity expected-volatility terms. Cboe’s VIX documentation states
that indicative VIX is calculated through 4:15 p.m. ET. The supplied CSVs are
retrospective daily OHLC histories and contain dates but no publication or
receipt timestamps. The empirical example therefore makes an explicit
4:15 p.m. ET availability assumption and never claims intraday alignment.

## Published dynamics

All `h` values are per-trading-day decimal log-return variances. Under P,
Equation (1) and the Equation (5) variance recursion are

```text
log(S_t/S_{t-1}) = r_t + lambda1 h_t + sqrt(h_t) z_{1,t}

h_t = omega + beta h_{t-1}
      + alpha (z_{1,t-1} - gamma1 sqrt(h_{t-1}))^2
      + (rho/k) sum_i=1^k
          (epsilon_{i,t-1} - gamma2 sqrt(h_{t-1}))^2.
```

The `epsilon_i` are iid standard normal and independent of `z_1`. `k=1` is
the literal two-Gaussian-shock model fitted by the empirical entry point.

Under Q, Equations (3) and (6) are

```text
log(S_t/S_{t-1}) = r_t - h_t/2 + sqrt(h_t) z*_{1,t}

gamma1* = gamma1 + lambda1 + 1/2
gamma2* = gamma2 + lambda2

h_t = omega + beta h_{t-1}
      + alpha (z*_{1,t-1} - gamma1* sqrt(h_{t-1}))^2
      + (rho/k) sum_i=1^k
          (epsilon*_{i,t-1} - gamma2* sqrt(h_{t-1}))^2.
```

Equations (7)–(12) imply

```text
c   = omega + alpha + rho
p   = beta + alpha gamma1^2  + rho gamma2^2
p*  = beta + alpha gamma1*^2 + rho gamma2*^2

E^P[h_next | h] = c + p h       mu  = c / (1 - p)
E^Q[h_next | h] = c + p* h      mu* = c / (1 - p*).
```

The implementation requires nonnegative `omega,beta`, positive `alpha,rho`,
positive integer `k`, positive state, and `p,p* < 1`. These are sufficient
numerical restrictions, not a claimed primary-source theorem.

## Physical estimation and the latent variance shock

Daily returns do not reveal `epsilon_t`. Replacing it by zero or by its
expected squared contribution would create a deterministic variance filter
that is not the stated two-shock model. `estimate_physical_dynamics` instead
uses a seeded bootstrap particle likelihood:

1. Particles represent the predictive distribution of `h_t`.
2. For each observed return, each particle receives its Equation (1) normal
   density weight.
3. Systematic resampling uses the normalized observation weights.
4. The observed-return shock is recovered as
   `(return-r-lambda1*h)/sqrt(h)` for the selected particle.
5. A new independent standard-normal `epsilon` is drawn for every particle and
   passed through the complete Equation (5) recursion.

The seed, particle count, likelihood, optimizer status, and filtered-state
quantiles are artifacts. Common random numbers make optimizer evaluations
reproducible for a fixed NumPy version. The fitted state remains a simulated
approximation. After fitting, two additional particle seeds re-evaluate the
fixed parameters and the artifact reports the cross-seed standard deviation of
average log likelihood. This diagnoses simulation sensitivity but is not a
parameter standard error; parameter uncertainty is not inferred.

The optimizer parameterization enforces the numerical restrictions at every
evaluation. It sets `c=mu*(1-p)`, allocates `c` by simplex shares to
`omega,alpha,rho`, and allocates `p` by simplex shares to
`beta,alpha*gamma1^2,rho*gamma2^2`. The equity-leverage branch constrains
`gamma1 >= 0`. Return-only likelihood is invariant to the sign of `gamma2`
because the latent normal shock is symmetric, so the fit records the explicit
identification convention `gamma2 >= 0`. `lambda1` is fitted with the physical
return density rather than supplied and relabelled as fitted.

The empirical example fits only returns ending 2019-12-03 through 2022-12-30.
Parameters are then frozen. The 250 returns in calendar 2023 are held out for
physical likelihood and residual diagnostics. Filtering may continue through
the 2024-01-03 cutoff with the frozen parameters to construct the state, but
those returns never re-enter fitting. No overlapping forecast labels or future
rows enter the physical objective. Because no historical daily curve was
supplied, Equation (1) uses an explicitly recorded zero per-session risk-free
log rate for both fitting and filtering; it is an assumption, not observed
rate data.

## Exact-cutoff VIX join and pricing-risk fit

`join_vix_closes_at_cutoff` requires an exact date for every named term. It
does not carry a prior close forward. Each expected term is either included or
emitted with a reason such as `no_exact_daily_close_on_cutoff_date` or
`duplicate_daily_closes_on_cutoff_date`.

The official target tenors are mapped to integer 252-day model periods as
follows:

| Index | Official target | Model periods | Mapping |
|---|---:|---:|---|
| VIX9D | 9 calendar days | 6 | `round(9*252/365)` |
| VIX | 30 calendar days | 21 | `round(30*252/365)` |
| VIX3M | 3 calendar months | 63 | `3/12*252` |
| VIX6M | 6 calendar months | 126 | `6/12*252` |
| VIX1Y | 1 calendar year | 252 | `252` |

This mapping is explicit but approximate. It does not reproduce Cboe’s exact
minute weighting, interpolation, or holiday handling.

Equations (19)–(20) give

```text
Hbar_market(tau) = (VIX_market(tau)/100)^2 / 252
Hbar_model(tau)  = (1/tau) sum_n=1^tau E_t^Q[h_{t+n}]
VIX_model(tau)   = 100 sqrt(252 Hbar_model(tau)).
```

The bounded cross-sectional fit minimizes the weighted sum of squared Equation
(30) errors `(VIX_market-VIX_model)/(100*sqrt(252))`. Physical parameters,
`lambda1`, and cutoff state are frozen; only constant `lambda2` is fitted.
Bounds are intersected with `p* < 1` and must select one side of
`lambda2=-gamma2`. The term structure identifies `p*`, not the sign of
`gamma2+lambda2`, so the symmetric observationally equivalent `lambda2` is
reported. RMSE, MAE, maximum VIX-point error, objective, and optimizer details
are separate from the physical fit diagnostics.

## Horizon-aligned VRP and interpretation boundaries

For `H` trading-day intervals, both measures use the same cutoff state and
units:

```text
W_P = sum_n=1^H E_t^P[h_{t+n}]
W_Q = sum_n=1^H E_t^Q[h_{t+n}]
VRP = W_Q - W_P.
```

The LUCA artifact uses `Q-P`; the article’s Equation (13) uses a one-step
`P-Q` convention. Annualized volatility is `sqrt(W/(H/252))` after interval
variances are summed. The artifact keeps three different quantities separate:

- aggregate VRP is `W_Q-W_P`;
- surface-relative richness is an individual VIX close minus its fitted model
  term value; and
- option theoretical value is a discounted Q payoff expectation.

None is a trade score without an eligible print and event-time quote.

## European option pricing under Q

`price_european_options_monte_carlo` uses the complete Equation (6) state
transition. With a caller-supplied deterministic-carry forward `F_0`, it
simulates

```text
S_T = F_0 exp(sum_t[-h_t/2 + sqrt(h_t) z*_{1,t}])
call = D E^Q[(S_T-K)+]
put  = D E^Q[(K-S_T)+].
```

The same return shock drives the return and next variance, and independent
auxiliary `epsilon*` shocks drive the second variance component. The pricer
uses seeded PCG64 draws and adjacent antithetic pairs. It reports two or more
path-count checkpoints, pair-aware Monte Carlo standard errors, approximate
95% intervals, direct call/put/straddle estimates, the `D(F-K)` parity target
and residual, and the discounted-terminal martingale residual. It is bounded
to 500,000 paths and 756 trading-day periods.

An optional Black forward value is included only as
`approximate_lognormal_expected_cumulative_variance_benchmark_not_model_price`.
It uses `W_Q` and is not the GARCSH price. Cumulative variance alone does not
uniquely determine a terminal distribution or option price.

## Reproducible exploratory run

`research/examples/empirical_vrp.py` consumes only the supplied files, checks
their raw SHA-256 digests, and writes generated output outside Git. Its default
artifact uses the exact 2024-01-03 closes: SPX 4704.81; VIX9D 13.24; VIX 14.04;
VIX3M 16.04; VIX6M 18.08; and VIX1Y 20.51.

In the pinned reference run, the 776-return physical fit converged after 768
function evaluations. The held-out segment contains 250 returns. The selected
cutoff `h_next` particle mean was `9.819092524374754e-05`, with p05
`5.6865171359592794e-05` and p95 `0.00016465981974206025`. The five-term
pricing fit converged but had RMSE 2.2845 VIX points, a material structural
miss that must not be hidden.

At 21 trading days, `W_P=0.0026254354910152365`,
`W_Q=0.002371187338478375`, and LUCA `Q-P VRP=-0.0002542481525368615`.
This exploratory estimate is negative; the implementation does not force the
usual positive-VRP narrative.

The option illustration uses the actual archived SPX close but assumes it is
also the forward, assumes a zero rate/unit discount factor, rounds an
illustrative strike to 4705, assumes a 100 multiplier, and uses an unverified
2024-02-02 PM-settlement calendar candidate. There is no option print. Those
assumptions are machine-labelled and the result cannot support a buy/sell
claim.

Run it with the pinned environment:

```bash
python research/examples/empirical_vrp.py \
  --reference-dir /path/to/output/reference \
  --output /path/to/output/empirical-vrp.json
```

`research/examples/direct_vrp.py` remains a self-generated identity and
pricing illustration. It is useful for deterministic mechanics only and is
not empirical evidence.

## Artifact contracts and unresolved limitations

`luca.direct-vrp-empirical-result.v1` contains raw input hashes, retrospective
availability, historical cutoff assumptions, nonoverlapping sample boundaries,
physical and pricing diagnostics, state uncertainty, every VIX include/exclude
decision, horizon-aligned P/Q variance paths, Q pricing checkpoints, input
classification, warnings, and exclusions. It is suitable for offline app and
theoretical-replay consumers without implying that live readiness was checked.

Material limitations remain:

- the particle likelihood is approximate and no parameter uncertainty is
  estimated;
- return-only data weakly identify `lambda1`, innovation allocation, and the
  sign of `gamma2`;
- one constant `lambda2` and one state cannot match the supplied VIX curve
  closely;
- daily closes do not prove contemporaneous historical receipt or intraday
  alignment;
- exact forward, discount curve, verified contract listing, print, and NBBO
  are absent; and
- the exact pricing-kernel equation and complete primary-source admissibility
  theorem remain unavailable, even though the printed Q transition is enough
  for the controlled simulation implemented here.
