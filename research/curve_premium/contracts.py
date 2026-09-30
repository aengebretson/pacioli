"""Separate ATM observation and future dollar comparison interfaces.

These functions require supplied qualified evidence. They acquire no data,
price no option, choose no hedge, and execute no transaction.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math

ATM_SCHEMA = 'luca.curve-premium-atm-input.v1'
DOLLAR_SCHEMA = 'luca.curve-premium-dollar-input.v1'


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps require timezone offsets')
    return result.astimezone(timezone.utc)


def decimal_value(value, *, positive=False):
    # Monetary quantities are decimal strings; never infer currency or multiplier.
    if not isinstance(value, str):
        raise ValueError('dollar/price/multiplier fields must be decimal strings')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError('invalid nonnegative/positive decimal')
    return result


def require_evidence(value, names):
    for name in names:
        item = value[name]
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f'{name} requires a nonempty evidence/reference string')


def atm_observation(request):
    """Return strike-dependent IV^2*tau and excess, never a strip expectation.

    ATM choice, IV extraction and W_P are caller responsibilities, with exact
    common cutoff/horizon required. Normal-premium fitting remains chronological.
    No automatic conversion from the unqualified daily-option export exists.
    """
    if request['schema_version'] != ATM_SCHEMA or request['study'] != 'atm_option_iv_proxy':
        raise ValueError('ATM interface does not accept VIX proxies')
    require_evidence(request, ['instrument_id', 'underlying_id', 'contract_evidence',
        'availability_evidence', 'settlement_evidence', 'iv_method', 'iv_side',
        'atm_selection_rule', 'atm_selection_evidence', 'forward_evidence',
        'discount_evidence', 'physical_forecast_id', 'source_sha256'])
    if request['underlying_id'] != 'SPX' or request['option_right'] not in ['C', 'P']:
        raise ValueError('expected identified SPX call or put')
    if request['settlement_style'] not in ['AM', 'PM']:
        raise ValueError('settlement style must be explicit')
    cutoff = timestamp(request['information_cutoff'])
    observed = timestamp(request['observed_at'])
    available = timestamp(request['available_at'])
    expiry = timestamp(request['payoff_fixing_at'])
    payment = timestamp(request['payment_at'])
    if not observed <= available <= cutoff < expiry <= payment:
        raise ValueError('invalid observation/availability/fixing/payment chronology')
    if timestamp(request['forward_available_at']) > cutoff or timestamp(request['discount_available_at']) > cutoff:
        raise ValueError('forward/discount unavailable at cutoff')
    if len(request['source_sha256']) != 64 or any(c not in '0123456789abcdef' for c in request['source_sha256']):
        raise ValueError('source_sha256 must identify the immutable supplied source')
    if timestamp(request['physical_information_cutoff']) != cutoff or timestamp(request['physical_horizon_start']) != cutoff or timestamp(request['physical_horizon_end']) != expiry:
        raise ValueError('ATM physical and implied horizons/cutoffs must match exactly')
    if request['day_count'] != 'ACT/365F' or request['iv_units'] != 'annual_decimal':
        raise ValueError('unsupported IV tenor/units; explicit upstream conversion required')
    strike = decimal_value(request['strike_points'], positive=True)
    forward = decimal_value(request['forward_points'], positive=True)
    decimal_value(request['discount_factor'], positive=True)
    tau = (expiry-cutoff).total_seconds()/(365*86400)
    iv, wp = float(request['iv']), float(request['W_P'])
    if not math.isfinite(iv) or iv <= 0 or not math.isfinite(wp) or wp < 0:
        raise ValueError('invalid IV/physical cumulative variance')
    if not math.isclose(float(request['tau_years']), tau, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError('tau does not match exact fixing horizon')
    wm = iv*iv*tau
    return {'schema_version': 'luca.curve-premium-atm-observation.v1',
        'study': 'atm_option_iv_proxy', 'instrument_id': request['instrument_id'],
        'information_cutoff': request['information_cutoff'], 'payoff_fixing_at': request['payoff_fixing_at'],
        'tau_act365': tau, 'W_market': wm, 'W_P': wp, 'observed_excess': wm-wp,
        'strike_over_forward': str(strike/forward),
        'interpretation': 'Strike-dependent IV-squared tenor proxy; not model-free expected variance, exact option fair value or executable edge.'}


def dollar_comparison(request):
    """Future qualified two-leg dollar boundary, with explicit missing economics.

    The externally supplied valuation interval must already include the
    declared uncertainty sources. Margins are deterministic indicative gaps,
    not fills, profit estimates, or a recommendation. An input residual/z-score
    cannot be substituted for an independent dollar valuation.
    """
    if request['schema_version'] != DOLLAR_SCHEMA or request['currency'] != 'USD':
        raise ValueError('unsupported dollar comparison schema/currency')
    require_evidence(request, ['valuation_id', 'valuation_method', 'valuation_uncertainty_scope',
        'omitted_uncertainty', 'simultaneous_quote_evidence', 'eligibility_evidence',
        'cost_assumptions', 'hedge_policy', 'hedge_instrument', 'hedge_rounding', 'hedge_basis_risk',
        'exit_policy', 'exit_horizon', 'exit_liquidity_assumption', 'tail_risk_limit',
        'margin_feasibility_evidence'])
    cutoff = timestamp(request['information_cutoff'])
    if timestamp(request['valuation_available_at']) > cutoff:
        raise ValueError('valuation unavailable at cutoff')
    if timestamp(request['valuation_information_cutoff']) != cutoff:
        raise ValueError('valuation information cutoff must match comparison cutoff')
    if any(x in request['valuation_method'].lower() for x in ['z-score', 'variance residual']):
        raise ValueError('variance diagnostics are not dollar valuations')
    legs=request['legs']
    if len(legs)!=2 or {leg['right'] for leg in legs}!={'C','P'}:
        raise ValueError('two-leg call/put pair required')
    identity=('underlying_id','strike_points','payoff_fixing_at','payment_at','settlement_style','multiplier','quantity')
    if any(legs[0][k]!=legs[1][k] for k in identity):
        raise ValueError('pair contract identity, horizon, multiplier and quantity must match')
    if sorted(request['valuation_leg_ids']) != sorted(leg['instrument_id'] for leg in legs):
        raise ValueError('external valuation must identify these exact legs')
    if decimal_value(request['valuation_quantity'], positive=True) != decimal_value(legs[0]['quantity'], positive=True):
        raise ValueError('valuation quantity differs from quote comparison')
    if timestamp(request['valuation_payoff_fixing_at']) != timestamp(legs[0]['payoff_fixing_at']) or timestamp(request['valuation_payment_at']) != timestamp(legs[0]['payment_at']):
        raise ValueError('valuation fixing/payment horizons differ')
    ask_total=Decimal(0);bid_total=Decimal(0)
    for leg in legs:
        require_evidence(leg,['instrument_id','quote_id','contract_evidence'])
        observed,available=timestamp(leg['observed_at']),timestamp(leg['available_at'])
        if not observed<=available<=cutoff<timestamp(leg['payoff_fixing_at'])<=timestamp(leg['payment_at']):
            raise ValueError('leg chronology invalid')
        age=(cutoff-observed).total_seconds()
        max_age=float(request['max_quote_age_seconds'])
        if not math.isfinite(max_age) or max_age<0 or age>max_age:
            raise ValueError('quote too old')
        bid,ask=decimal_value(leg['bid_points']),decimal_value(leg['ask_points'])
        quantity=decimal_value(leg['quantity'],positive=True)
        multiplier=decimal_value(leg['multiplier'],positive=True)
        if quantity!=quantity.to_integral_value():raise ValueError('integer contract quantity required')
        if bid>ask or decimal_value(leg['bid_size'])<quantity or decimal_value(leg['ask_size'])<quantity:
            raise ValueError('crossed quote or insufficient displayed size')
        ask_total+=ask*quantity*multiplier;bid_total+=bid*quantity*multiplier
    skew=abs((timestamp(legs[0]['observed_at'])-timestamp(legs[1]['observed_at'])).total_seconds())
    max_skew=float(request['max_leg_skew_seconds'])
    if not math.isfinite(max_skew) or max_skew<0 or skew>max_skew:
        raise ValueError('leg observation skew too large')
    lo=decimal_value(request['total_position_fair_value_lower_usd'])
    hi=decimal_value(request['total_position_fair_value_upper_usd'])
    if lo>hi:raise ValueError('invalid external valuation interval')
    costs=sum((decimal_value(request[k]) for k in ['fees_usd','entry_slippage_usd','hedge_cost_budget_usd','exit_cost_budget_usd','financing_cost_budget_usd','additional_uncertainty_reserve_usd']),Decimal(0))
    return {'schema_version':'luca.curve-premium-dollar-result.v1','currency':'USD',
        'both_asks_usd':str(ask_total),'both_bids_usd':str(bid_total),'cost_and_reserve_usd':str(costs),
        'indicative_buy_margin_usd':str(lo-ask_total-costs),
        'indicative_sell_margin_usd':str(bid_total-hi-costs),
        'execution_edge_established':False,'fills_established':False,'profitability_established':False,
        'interpretation':'Externally supplied valuation bounds versus displayed quotes and declared budgets. Does not establish simultaneous fills, financing/margin feasibility, hedge outcomes or exits.'}
