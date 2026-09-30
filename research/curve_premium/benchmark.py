"""Chronological normal-premium benchmark. Run forecast and score separately."""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path

# Reuse this assigned review baseline only; never import another worktree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from luca_research.estimators import historical_variance, ewma_variance, flat_variance_forecast
from luca_research.garch import fit_garch11, GarchFitFailure
from common import canonical_hash, checkpoint, digest, existing_output, now, record, write_json

SCHEMA = 'luca.curve-premium-forecast.v1'


def load_inputs(reference):
    prices = {}
    with (reference / 'daily/index.csv').open(newline='') as stream:
        for row in csv.reader(stream):
            if len(row) != 6 or row[1] != 'spx-index':
                raise ValueError('SPX schema/identity mismatch')
            day, close = date.fromisoformat(row[2]), float(row[3])
            if not math.isfinite(close) or close <= 0 or day in prices:
                raise ValueError('invalid or duplicate SPX date')
            prices[day] = close
    dates = sorted(prices)
    vix = {}
    for name in ['VIX9D', 'VIX', 'VIX3M', 'VIX6M', 'VIX1Y']:
        values = {}
        with (reference / 'vix' / (name + '_History.csv')).open(newline='') as stream:
            for row in csv.DictReader(stream):
                day = datetime.strptime(row['DATE'], '%m/%d/%Y').date()
                value = float(row['CLOSE'])
                if not math.isfinite(value) or value <= 0 or day in values:
                    raise ValueError('invalid or duplicate VIX date')
                values[day] = value
        vix[name] = values
    return dates, prices, vix


def fit_normal(rows, model, x):
    y = np.asarray([r['observed_excess_annualized'] for r in rows], dtype=float)
    xs = np.asarray([r['physical_annualized'] for r in rows], dtype=float)
    center, scale = float(np.mean(xs)), float(np.std(xs))
    if model == 'trailing_mean':
        coefficients = [float(np.mean(y))]
        fitted = np.full(len(y), coefficients[0])
        predicted = coefficients[0]
    elif model == 'trailing_median':
        coefficients = [float(np.median(y))]
        fitted = np.full(len(y), coefficients[0])
        predicted = coefficients[0]
    elif model == 'linear_physical_variance':
        if scale <= 1e-15:
            raise ValueError('conditional predictor has zero training scale')
        design = np.column_stack([np.ones(len(y)), (xs - center) / scale])
        beta = np.linalg.lstsq(design, y, rcond=None)[0]
        coefficients = beta.tolist()
        fitted = design @ beta
        predicted = float(beta[0] + beta[1] * (x - center) / scale)
    else:
        raise ValueError('unknown premium model')
    return predicted, {'coefficients': coefficients, 'predictor_train_center': center,
        'predictor_train_scale': scale, 'training_rmse_annualized_descriptive_only': float(np.sqrt(np.mean((y-fitted)**2))),
        'training_bias_annualized_descriptive_only': float(np.mean(y-fitted))}


def forecast(args, spec, out):
    if (out / 'forecast-seal.json').exists() or (out / 'forecasts.jsonl').exists():
        raise ValueError('Refuse to revise saved forecasts; use a new output directory')
    dates, prices, vix = load_inputs(args.reference)
    indexes = {d: i for i, d in enumerate(dates)}
    # Outcome prices remain inaccessible to physical_fit: only this past slice is passed.
    returns = [math.log(prices[b] / prices[a]) for a, b in zip(dates, dates[1:])]
    parts = spec['partitions']
    eligible = [d for d in dates if parts['premium_warmup_start'] <= d.isoformat() <= parts['evaluation_end']]
    history = defaultdict(lambda: deque(maxlen=spec['premium_fit_observations']))
    errors = defaultdict(lambda: deque(maxlen=126))
    exclusions, forecast_count, fit_count = Counter(), 0, 0
    input_files = [args.reference / 'daily/index.csv'] + sorted((args.reference / 'vix').glob('*_History.csv'))
    input_hashes = {str(p): digest(p) for p in input_files}
    checkpoint(out, 'Generating chronological forecasts before outcomes', origins=len(eligible))
    with (out/'forecasts.jsonl').open('x') as fs, (out/'fit-partitions.jsonl').open('x') as fits, (out/'physical-fits.jsonl').open('x') as physical_file, (out/'observations.jsonl').open('x') as obs_file, (out/'exclusions.jsonl').open('x') as excluded:
        for ordinal, day in enumerate(eligible):
            i = indexes[day]
            endpoints = {term: day + timedelta(days=days) for term, days in spec['terms'].items()}
            valid = {term: e for term, e in endpoints.items() if e in indexes and e.isoformat() <= parts['outcome_last_date'] and day in vix[term]}
            for term, end in endpoints.items():
                reason = ('outcome_right_censored' if end.isoformat() > parts['outcome_last_date'] else
                          'calendar_endpoint_absent' if end not in indexes else
                          'same_date_vix_absent' if day not in vix[term] else None)
                if reason:
                    exclusions[reason] += 1
                    record(excluded, {'origin': str(day), 'term': term, 'reason': reason})
            if not valid:
                continue
            max_horizon = max(indexes[e]-i for e in valid.values())
            for physical, config in spec['physical_models'].items():
                window = config['window_returns']
                past = returns[max(0, i-window):i]
                if len(past) < window or dates[i-window].isoformat() < parts['physical_history_start']:
                    exclusions['insufficient_physical_history'] += 1
                    continue
                fit_id = f'{day}:{physical}'
                fit_info = {'id': fit_id, 'origin': str(day), 'physical_model': physical,
                    'first_return_start_date': str(dates[i-window]), 'first_return_end_date': str(dates[i-window+1]),
                    'last_return_end_date': str(day), 'return_count': window,
                    'returns_sha256': canonical_hash(past), 'config': config}
                try:
                    if physical == 'rolling':
                        value, _ = historical_variance(past, config['mean'])
                        path = flat_variance_forecast(value, max_horizon)
                        fit_info['one_step_variance'] = value
                    elif physical == 'ewma':
                        value, _ = ewma_variance(past, config['decay'], config['mean'])
                        path = flat_variance_forecast(value, max_horizon)
                        fit_info['one_step_variance'] = value
                    else:
                        fit_count += 1
                        if fit_count > spec['compute_bounds']['max_garch_fits']:
                            raise ValueError('GARCH fit budget exceeded')
                        fit = fit_garch11(past, horizon=max_horizon, mean=config['mean'],
                            max_iterations=config['max_iterations'], optimizer_tolerance=config['optimizer_tolerance'])
                        path = fit.conditional_variances
                        fit_info.update(parameters=fit.parameters_decimal, convergence=fit.convergence)
                except GarchFitFailure as exc:
                    exclusions['garch_failure'] += 1
                    record(excluded, {'origin': str(day), 'physical_model': physical, 'reason': str(exc), 'details': exc.details})
                    continue
                fit_info['forecast_variances'] = path
                record(physical_file, fit_info)
                for term, end in valid.items():
                    n = indexes[end]-i
                    tau = spec['terms'][term]/365.0
                    wp = math.fsum(path[:n])
                    x = wp/tau
                    observed_id = f'{day}:{term}:{physical}'
                    old = list(history[(term, physical)])
                    pending = []
                    if len(old) >= spec['premium_min_observations'] and str(day) >= parts['interval_calibration_start']:
                        for model in spec['premium_models']:
                            normal, diagnostics = fit_normal(old, model, x)
                            key = (term, physical, model)
                            prior_errors = list(errors[key])
                            band = None
                            if len(prior_errors) >= 63:
                                q = np.quantile([v['residual_annualized'] for v in prior_errors], [0.05,0.95])
                                band = [float((normal+q[0])*tau), float((normal+q[1])*tau)]
                            forecast_id = observed_id + ':' + model
                            partition = {'schema_version': 'luca.curve-premium-fit.v1', 'id': forecast_id,
                                'origin': str(day), 'physical_fit_id': fit_id, 'training_observation_ids': [r['id'] for r in old],
                                'training_first_date': old[0]['origin'], 'training_last_date': old[-1]['origin'],
                                'training_sha256': canonical_hash(old), 'interval_error_forecast_ids': [v['id'] for v in prior_errors],
                                **diagnostics}
                            f = {'schema_version': SCHEMA, 'id': forecast_id, 'study': 'vix_strip_proxy_exploratory',
                                'origin': str(day), 'decision_time_local': str(day)+'T17:00:00', 'decision_timezone': 'America/New_York',
                                'horizon_end': str(end), 'horizon_calendar_days': spec['terms'][term],
                                'forecast_intervals': n, 'tau_act365': tau, 'term': term, 'physical_model': physical,
                                'premium_model': model, 'fit_partition_id': forecast_id, 'W_P': wp,
                                'predicted_normal_excess': normal*tau, 'predicted_W_market_proxy': wp+normal*tau,
                                'excess_prediction_band': band, 'prediction_band_error_count': len(prior_errors),
                                'partition': 'exploratory_evaluation' if str(day) >= parts['evaluation_start'] else 'interval_warmup',
                                'created_at': now()}
                            if not all(math.isfinite(f[k]) for k in ['W_P','predicted_normal_excess','predicted_W_market_proxy']):
                                raise ValueError('nonfinite forecast')
                            record(fits, partition)
                            record(fs, f)
                            pending.append((key, f))
                            forecast_count += 1
                    else:
                        exclusions['premium_fit_warmup'] += 1
                    # Commit the prediction and its earlier fit before judging this quote.
                    fs.flush(); fits.flush()
                    wm = (vix[term][day]/100.0)**2*tau
                    obs = {'id': observed_id, 'origin': str(day), 'term': term, 'physical_model': physical,
                        'horizon_end': str(end), 'W_market': wm, 'W_P': wp, 'observed_excess': wm-wp,
                        'observed_excess_annualized': (wm-wp)/tau, 'physical_annualized': x}
                    record(obs_file, obs)
                    for key, f in pending:
                        errors[key].append({'id': f['id'], 'origin': str(day),
                            'residual_annualized': ((wm-wp)-f['predicted_normal_excess'])/tau})
                    history[(term, physical)].append(obs)
            if ordinal % 100 == 0:
                for stream in [fs,fits,physical_file,obs_file,excluded]:
                    stream.flush(); os.fsync(stream.fileno())
                checkpoint(out, 'Forecast checkpoint; no realized outcomes scored', origin=str(day), forecasts=forecast_count)
        for stream in [fs,fits,physical_file,obs_file,excluded]:
            stream.flush(); os.fsync(stream.fileno())
    sealed = ['forecasts.jsonl','fit-partitions.jsonl','physical-fits.jsonl','observations.jsonl','exclusions.jsonl','predeclaration.json']
    write_json(out/'forecast-seal.json', {'schema_version': 'luca.curve-premium-seal.v1',
        'sealed_at': now(), 'forecasts': forecast_count, 'garch_fit_attempts': fit_count,
        'exclusion_counts': dict(exclusions), 'input_sha256': input_hashes,
        'artifacts_sha256': {name:digest(out/name) for name in sealed}})
    checkpoint(out, 'Forecast files sealed; outcomes not yet scored', forecasts=forecast_count)


def corr(a, b):
    if len(a)<3 or np.std(a)==0 or np.std(b)==0:
        return None
    return float(np.corrcoef(a,b)[0,1])


def describe(values, lag):
    x = np.asarray(values,dtype=float)
    if not len(x):
        return {'n':0}
    centered = x-x.mean()
    v = float(np.mean(centered**2))
    n = len(x)
    lag = min(lag,n-1)
    lrv = float(centered@centered)/n
    for k in range(1,lag+1):
        lrv += 2*(1-k/(lag+1))*float(centered[k:]@centered[:-k])/n
    se = math.sqrt(max(0,lrv)/n) if n>1 else None
    return {'n':n,'mean':float(x.mean()),'std_ddof1':float(x.std(ddof=1)) if n>1 else None,
        'rmse':float(np.sqrt(np.mean(x*x))), 'quantiles':dict(zip(['p01','p05','p50','p95','p99'],np.quantile(x,[.01,.05,.5,.95,.99]).tolist())),
        'skewness':float(np.mean(centered**3)/v**1.5) if v>0 else None,
        'excess_kurtosis':float(np.mean(centered**4)/v**2-3) if v>0 else None,
        'lag1_correlation':corr(x[:-1],x[1:]),'squared_lag1_correlation':corr(x[:-1]**2,x[1:]**2),
        'hac_mean_standard_error':se,'hac_lag':lag,
        'approximate_95_mean_interval': [float(x.mean()-1.96*se),float(x.mean()+1.96*se)] if se is not None and n>=20 else None,
        'uncertainty_note':'Bartlett HAC plug-in, no parameter/vintage uncertainty. Asymptotic mean interval suppressed below 20 observations; overlapping rows are dependent.'}


def group_summary(rows, days, nonoverlap=False):
    residual = np.array([r['residual'] for r in rows])
    x = np.array([r['W_P']/r['tau_act365'] for r in rows])
    lag = min(2, max(0,len(rows)-1)) if nonoverlap else math.ceil(days*252/365)
    bands = [r for r in rows if r['excess_prediction_band'] is not None]
    scales = []
    if len(rows)>=9:
        # Descriptive binning only; these full-evaluation quantiles never feed forecasts.
        edges = np.quantile(x,[1/3,2/3])
        for label, mask in [('low',x<=edges[0]),('middle',(x>edges[0])&(x<=edges[1])),('high',x>edges[1])]:
            z=residual[mask]
            scales.append({'physical_variance_tercile':label,'n':len(z),'residual_rms':float(np.sqrt(np.mean(z*z))) if len(z) else None})
    return {'residual':describe(residual,lag),
        'observed_excess':describe([r['observed_excess'] for r in rows],lag),
        'physical_error_WP_minus_realized':describe([r['W_P']-r['realized_variance'] for r in rows],lag),
        'corr_absolute_residual_with_physical_variance':corr(abs(residual),x),
        'heteroskedasticity_descriptive_scales':scales,
        'normal_excess_MAE':float(np.mean(abs(residual))) if len(rows) else None,
        'interval_coverage':sum(r['excess_prediction_band'][0]<=r['observed_excess']<=r['excess_prediction_band'][1] for r in bands)/len(bands) if bands else None,
        'interval_count':len(bands),
        'predictive_diagnostics': {'corr_residual_with_Wmarket_minus_realized':corr(residual,[r['W_market']-r['realized_variance'] for r in rows]),
            'corr_residual_with_realized_minus_WP':corr(residual,[r['realized_variance']-r['W_P'] for r in rows]),
            'interpretation':'Exploratory non-overlapping-origin association, shared-component mechanical coupling; neither incremental predictive proof nor an executable payoff.'} if nonoverlap else None}


def score(args,spec,out):
    seal=json.loads((out/'forecast-seal.json').read_text())
    supplied = [args.reference / 'daily/index.csv'] + sorted((args.reference / 'vix').glob('*_History.csv'))
    if {str(p.resolve()) for p in supplied} != {str(Path(p).resolve()) for p in seal['input_sha256']}:
        raise ValueError('Scoring reference paths differ from the sealed forecast inputs')
    for name,sha in seal['artifacts_sha256'].items():
        if digest(out/name)!=sha: raise ValueError('forecast/partition/predeclaration changed since seal')
    for path,sha in seal['input_sha256'].items():
        if digest(path)!=sha: raise ValueError('input changed since forecast')
    dates,prices,_=load_inputs(args.reference)
    ix={d:i for i,d in enumerate(dates)}
    observations={r['id']:r for r in map(json.loads,(out/'observations.jsonl').read_text().splitlines())}
    forecasts=[json.loads(line) for line in (out/'forecasts.jsonl').read_text().splitlines()]
    groups=defaultdict(list)
    # One physical-model-independent origin schedule per tenor, selected without prices/outcomes.
    schedules={}
    for term,days in spec['terms'].items():
        origins=sorted({r['origin'] for r in forecasts if r['term']==term and r['partition']=='exploratory_evaluation'})
        chosen=[]; next_day='0001-01-01'
        for d in origins:
            if d>=next_day:
                chosen.append(d);next_day=str(date.fromisoformat(d)+timedelta(days=days))
        schedules[term]=chosen
    with (out/'scored-observations.jsonl').open('x') as stream:
        for f in forecasts:
            if f['partition']!='exploratory_evaluation':continue
            start,end=date.fromisoformat(f['origin']),date.fromisoformat(f['horizon_end'])
            rv=math.fsum(math.log(prices[dates[j]]/prices[dates[j-1]])**2 for j in range(ix[start]+1,ix[end]+1))
            o=observations[f['id'].rsplit(':',1)[0]]
            row={**f,'W_market':o['W_market'],'observed_excess':o['observed_excess'],
                 'residual':o['observed_excess']-f['predicted_normal_excess'], 'realized_variance':rv,
                 'outcome_available_date':str(end), 'nonoverlap_origin':f['origin'] in schedules[f['term']]}
            record(stream,row);groups[(f['term'],f['physical_model'],f['premium_model'])].append(row)
    summaries=[]
    for (term,physical,premium),rows in sorted(groups.items()):
        days=spec['terms'][term]
        selected=[r for r in rows if r['nonoverlap_origin']]
        summaries.append({'term':term,'physical_model':physical,'premium_model':premium,
            'horizon_days':days,'daily_overlapping_descriptive':group_summary(rows,days),
            'nonoverlapping_primary':group_summary(selected,days,True)})
    result={'schema_version':'luca.curve-premium-result.v1','study':'vix_strip_proxy_exploratory',
        'created_at':now(),'forecast_seal_sha256':digest(out/'forecast-seal.json'),
        'predeclaration_sha256':digest(out/'predeclaration.json'),'no_untouched_holdout':True,
        'scored_records':sum(len(x) for x in groups.values()),'candidate_groups':summaries,
        'nonoverlap_schedules':schedules,'exclusions':seal['exclusion_counts'],
        'atm_study':{'status':'interface_only','actual_history_scored':False},
        'claims':{'executable_edge':False,'exact_option_value':False,'fills':False,'profitability':False,'integrated':False},
        'prediction_band_scope':spec['prediction_interval'],'timing':spec['timing']}
    write_json(out/'benchmark-result.json',result)
    report(result,spec,out)
    checkpoint(out,'Outcome scoring complete',scored_records=result['scored_records'],groups=len(summaries))


def report(result,spec,out):
    lines=['# Chronological normal-premium benchmark — exploratory VIX-strip study','',
        'All supplied 2023–2025 history was previously inspected. This chronological evaluation is not an untouched holdout and makes no ATM trading, fair-value, fill, profitability or integration claim.','',
        '## Definitions and chronology','',
        '`W_market=(VIX_term/100)^2*(D/365)`, `W_P=sum forecast daily variances` over the identical D-calendar-day interval. Observed excess is Q-minus-P: `W_market-W_P`. Predicted normal excess uses strictly earlier observations; residual is observed excess minus predicted normal excess. This normal premium is a statistical conditional expectation of a proxy discrepancy, not an identified economic risk premium. Errors in W_P and the market proxy remain in it.','',
        'Same-date daily inputs are assumed available by 17:00 New York. The SPX close anchors daily returns; VIX clocks, receipt vintages and exact close alignment are unverified. These are date/tenor-matched proxies, not exact timestamp-matched expectations. Endpoints absent from the supplied SPX schedule are excluded. No rounded 21-session replacement for 30 days is used.','',
        'Rolling 63-return zero-mean variance, 252-return EWMA (0.94), and 504-return zero-mean normal GARCH(1,1) reuse the Q1 implementations. Normal models use up to 252 prior observations, minimum 126: mean, median and one OLS intercept/slope on W_P/tau with training-only centering/scaling. Premium labels are observed discrepancies known at their own close; they require no future realized outcomes.','',
        'Forecaster writes each partition and prediction before reading the quote being judged into its premium history. All forecast/partition files are sealed before realized-outcome scoring. Stored historical data do not prove historical publication availability.','',
        '## Sensitivity (non-overlapping primary origins)','',
        'Variance units below are decimal squared returns. Different tenors have different origin schedules and counts; do not rank raw RMSE across tenors or pool model/tenor rows as independent experiments.','',
        '| Term | Physical | Normal model | n | Mean residual | Residual RMSE | Physical RMSE | Band coverage |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for s in result['candidate_groups']:
        a=s['nonoverlapping_primary'];r=a['residual'];p=a['physical_error_WP_minus_realized']
        c=a['interval_coverage'];cs=f'{c:.3f}' if c is not None else 'n/a'
        lines.append(f"| {s['term']} | {s['physical_model']} | {s['premium_model']} | {r['n']} | {r.get('mean',0):.6g} | {r.get('rmse',0):.6g} | {p.get('rmse',0):.6g} | {cs} |")
    thirty = [g for g in result['candidate_groups'] if g['term'] == 'VIX']
    if thirty:
        errors = [g['nonoverlapping_primary']['residual']['rmse'] for g in thirty]
        coverages = [g['nonoverlapping_primary']['interval_coverage'] for g in thirty]
        lines += ['', '## Observed behavior (no candidate selection)', '',
            f"The run scored {result['scored_records']:,} dependent model/tenor records. Non-overlapping origin counts by term are "
            + ', '.join(f'{k}: {len(v)}' for k,v in result['nonoverlap_schedules'].items()) + '.', '',
            f'Across the nine 30-day candidates, primary residual RMSE ranges from {min(errors):.6g} to {max(errors):.6g}; empirical band coverage ranges from {min(coverages):.1%} to {max(coverages):.1%}. This sensitivity does not select or validate a model.', '']
        lines += ['The following comparable 30-day trailing-mean cases show how the physical forecast changes residual diagnostics. These are examples of all three physical methods, not a preferred estimator.', '',
            '| Physical | Primary bias | Primary std | Primary lag-1 | Primary excess kurtosis | Daily-row lag-1 | Daily abs-error/state correlation |',
            '|---|---:|---:|---:|---:|---:|---:|']
        for g in thirty:
            if g['premium_model'] != 'trailing_mean':
                continue
            a = g['nonoverlapping_primary']['residual']
            b = g['daily_overlapping_descriptive']
            lines.append(f"| {g['physical_model']} | {a['mean']:.6g} | {a['std_ddof1']:.6g} | {a['lag1_correlation']:.3f} | {a['excess_kurtosis']:.3f} | {b['residual']['lag1_correlation']:.3f} | {b['corr_absolute_residual_with_physical_variance']:.3f} |")
        lines += ['', 'Residual persistence, changing scale and non-Gaussian tails remain after subtracting a normal premium. A centered average does not establish white-noise errors. At 93–366 days, 2–11 non-overlapping origins cannot support stable tail or mean-uncertainty claims; the JSON retains descriptive values and suppresses the asymptotic mean interval below 20 origins.', '']
    lines += ['', '## Diagnostics and uncertainty','',
        'benchmark-result.json reports bias, standard deviation, RMSE, lag-one and squared-residual persistence, absolute-error/physical-variance correlation, descriptive tercile scales, quantiles, skewness, excess kurtosis, coverage and physical forecast errors for every candidate. Full-evaluation terciles appear only in descriptive diagnostics, never in fitting. Saved training RMSE/bias are descriptive fit, not prediction scores.','',
        'Daily overlapping observations are descriptive. Their mean uncertainty uses Bartlett/Newey-West lags ceil(D*252/365). Primary origins share no return intervals within a tenor; remaining serial dependence uses HAC lag 2. Asymptotic mean intervals are suppressed below 20 origins. Long-horizon estimates and tail metrics from few origins are unstable. No multiplicity-adjusted superiority claim is made.','',
        'Prediction bands use the 5th/95th quantiles of the last 126 previously saved forecast residuals (minimum 63), not in-sample regression residuals. They include historical proxy-error dispersion only. Parameter, physical-model, measurement/vintage, regime, joint-tenor, option-price and execution uncertainty are omitted. Dependence means nominal 90% coverage is not guaranteed.','',
        'Predictive diagnostics correlate residuals with subsequent market-minus-realized variance and realized-minus-W_P on non-overlapping origins. Shared W_market/W_P terms can create mechanical correlations; these do not establish incremental forecasting information or profitability. Realized variance uses squared daily log returns and omits intraday variation and option payoff/tail detail.','',
        '## Gaps and next action','',
        'Daily option records have unverified clocks, settlement and vendor-IV conventions. The September 2026 replay is a single session with zero qualified synchronized point decisions and unresolved causal rate/forward inputs. No exact matched ATM rows are scored. contracts.py and schemas.json define a separate strict ATM input boundary and a future dollar comparison boundary. Neither supplies missing quotes or prices.','',
        'Review the frozen specification and artifact reconciliation. For stronger evidence, provide an immutable known-at-decision ATM contract/quote/forward/discount record with verified fixing and payment times. Reserve post-2026-09-30 dates for future confirmation with no retuning of this history.','',
        '## Primary methodology source','',
        '[Cboe Selected SPX Target Expected Volatility Term Indices Methodology, sections 1–3](https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_SPX_Target_Expected_Volatility_Term_Indices.pdf) describes strike-strip indices and 9/30/93/184/366-day targets. The current methodology is documentation, not proof of historical methodology vintages. ATM IV squared times tenor is strike-dependent and is not a model-free variance expectation.','']
    (out/'benchmark-report.md').write_text('\n'.join(lines))


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['forecast','score']);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',required=True)
    args=p.parse_args();out=existing_output(args.output);spec=json.loads((out/'predeclaration.json').read_text())
    if spec['schema_version']!='luca.curve-premium-predeclaration.v1':raise ValueError('unknown predeclaration schema')
    (forecast if args.stage=='forecast' else score)(args,spec,out)


if __name__=='__main__':main()
