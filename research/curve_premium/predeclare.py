"""Frozen exploratory specification; write before any outcome scoring."""
from __future__ import annotations

SPEC = {
    'schema_version': 'luca.curve-premium-predeclaration.v1',
    'study': 'vix_strip_proxy_exploratory',
    'history_status': 'All supplied 2023-2025 history was previously inspected. No untouched holdout.',
    'partitions': {
        'physical_history_start': '2018-01-01',
        'premium_warmup_start': '2021-01-01',
        'interval_calibration_start': '2022-01-01',
        'evaluation_start': '2023-01-01',
        'evaluation_end': '2025-12-31',
        'outcome_last_date': '2025-12-31',
        'future_confirmation': 'Dates after 2026-09-30, not acquired or scored here; freeze this specification and verify original availability vintages before future confirmation.'
    },
    'terms': {'VIX9D': 9, 'VIX': 30, 'VIX3M': 93, 'VIX6M': 184, 'VIX1Y': 366},
    'units': 'decimal log-return squared cumulative variance; tau=calendar_days/365; volatility inputs are index points divided by 100',
    'sign': 'Q-minus-P; observed_excess=W_market-W_P; residual=observed_excess-normal_excess',
    'physical_models': {
        'rolling': {'window_returns': 63, 'mean': 'zero'},
        'ewma': {'window_returns': 252, 'mean': 'zero', 'decay': 0.94},
        'garch_1_1': {'window_returns': 504, 'mean': 'zero', 'max_iterations': 200, 'optimizer_tolerance': 1e-7}
    },
    'premium_models': ['trailing_mean', 'trailing_median', 'linear_physical_variance'],
    'premium_fit_observations': 252,
    'premium_min_observations': 126,
    'conditional_model': 'OLS intercept plus same-origin W_P/tau only. Center and scale using earlier fit rows only. Fit target is earlier (W_market-W_P)/tau. No current market quote is a predictor.',
    'prediction_interval': {
        'level_label': 'empirical 90 percent prediction band, not guaranteed coverage',
        'method': '5th/95th quantiles of last 126 previously saved chronological forecast residuals, minimum 63, same model and tenor, expressed per calendar year then scaled by current tau',
        'includes': ['historical dispersion of model forecast errors in the observed excess proxy'],
        'omits': ['parameter estimation uncertainty', 'physical model uncertainty', 'vintage and timing error', 'proxy/measurement error decomposition', 'regime change', 'joint cross-tenor uncertainty', 'option price and execution uncertainty'],
        'dependence': 'Historical errors are dependent; this is not iid conformal coverage. Assess coverage descriptively and report HAC uncertainty separately.'
    },
    'timing': {
        'decision': '17:00 America/New_York on the observation date; hypothetical after-close research calculation, not an executable close trade',
        'spx_anchor': '16:00 America/New_York daily SPX close; early closes not independently verified',
        'market_observation': 'same-date official VIX-family daily CLOSE; historical close/publication times not verified; assume known by 17:00 solely for exploratory calculation',
        'premium_fit': 'strictly earlier dates only; target quote excluded from premium fit',
        'physical_fit': 'return observations through same-date SPX close, strictly no later returns',
        'horizon': 'exact D-calendar-day endpoint must be a supplied SPX close date; otherwise exclude. W_P sums forecast daily variances over identical future close intervals; no 252-to-365 tenor substitution.',
        'calendar': 'historical supplied SPX observation dates used as session schedule; holiday/listing vintages unverified; no future prices enter forecasts',
        'alignment_limit': 'VIX close and SPX close clocks are not exactly synchronized. Common date and tenor are an approximation, not exact matched timestamps or an ATM expiry.'
    },
    'outcomes': 'sum squared close-to-close SPX log returns on (origin, origin+D], zero mean; a discretely sampled realized-variance proxy, not continuous quadratic variation',
    'dependence': {
        'primary': 'Greedy non-overlapping origins separately per tenor from 2023-01-01, next origin >= previous endpoint. Same common origin schedule for all models; failures are missing, never replaced.',
        'secondary': 'Daily overlapping records are descriptive; Newey-West/Bartlett mean SE with lag ceil(D*252/365), capped at n-1. Cross-tenor/model rows are not independent trials.',
        'predictive': 'Report correlation of residual with W_market-realized_variance and with realized_variance-W_P on non-overlapping origins only; mechanical shared components prevent causal or trading interpretation; no model selection/p-values.'
    },
    'diagnostics': ['bias', 'std and RMSE', 'lag-one persistence', 'squared-residual persistence', 'correlation of absolute residual with physical variance', 'physical-variance tercile residual scale', 'quantiles', 'skewness', 'excess kurtosis', 'empirical interval coverage', 'physical forecast bias/RMSE', 'normal-excess loss and descriptive training fit'],
    'exclusions': ['invalid/nonpositive/duplicate conflicting closes fail input ingestion', 'missing same-date VIX: exclude, never forward fill', 'calendar endpoint absent: exclude', 'insufficient trailing history: exclude', 'GARCH failure: exclude that model, no fallback', 'outcome after 2025-12-31: right-censored', 'nonfinite model output: fail'],
    'seed': None,
    'compute_bounds': {'process_timeout_seconds': 1500, 'threads': 1, 'max_input_rows': 3000000, 'max_garch_fits': 1400},
    'selection_policy': 'All predeclared candidates reported; no retuning this inspected sample; no winning-model or trading-edge claim.',
    'atm_study': 'Interface only unless exact matched quote, contract, expiry, availability, forward, discount and IV conventions are verified; never pool with VIX.',
}
