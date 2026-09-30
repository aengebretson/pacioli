#!/usr/bin/env python3
"""Bounded, offline Q2-T17 audit. No network, input writes, fits or fill simulation."""
import argparse
import bisect
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import resource
import sys
import time

CALL = 'spxw_20261023_7725_call_bid_ask'
PUT = 'spxw_20261023_7725_put_bid_ask'
ES = 'esz6_bid_ask'
SPX = 'spx_index_observations'
VIX = ['vix_index_observations', 'vix9d_index_observations', 'vix3m_index_observations', 'vix6m_index_observations', 'vix1y_index_observations']
QUOTES = [CALL, PUT, ES]
CORE = [CALL, PUT, SPX, ES]
NAMES = CORE + VIX

def epoch(x):
    return int(datetime.fromisoformat(x.replace('Z', '+00:00')).timestamp())

def utc():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return {'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': h.hexdigest()}

def save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    tmp.replace(path)

def checkpoint(out, phase):
    p = out / 'STATUS.json'
    d = json.loads(p.read_text()) if p.exists() else {'task': 'Q2-T17'}
    d.update(updated_at=utc(), phase=phase, status='in_progress')
    save(p, d)
    with (out / 'STATUS.md').open('a') as f:
        f.write(f'\n- {d["updated_at"]}: {phase}\n')
    inbox = out / 'INBOX.md'
    if inbox.exists():
        print('INBOX:', inbox.read_text().strip(), flush=True)

def describe(values):
    if not values:
        return {'n': 0}
    s = sorted(values)
    # Nearest-rank quantiles: no interpolated market observations.
    import math
    return {'n': len(s), 'min': float(s[0]), 'p50': float(s[math.ceil(.5 * len(s))-1]),
            'p95': float(s[math.ceil(.95 * len(s))-1]), 'max': float(s[-1])}

def dec(x):
    return Decimal(str(x))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out, inp = args.output.resolve(), args.input.resolve()
    if out == inp or inp in out.parents or '.git' in out.parts or 'worktrees' in out.parts:
        raise ValueError('Output must be an external runtime directory, separate from inputs')
    out.mkdir(parents=True, exist_ok=True)
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024**2, 1536 * 1024**2))
    began = time.monotonic()
    declaration = out / 'predeclaration.json'
    config = json.loads(declaration.read_text())
    receipt = json.loads((out / 'predeclaration-receipt.json').read_text())
    if digest(declaration)['sha256'] != receipt['sha256']:
        raise ValueError('Predeclaration hash mismatch')
    start, end = map(epoch, config['evaluation'])
    cstart, cend = map(epoch, config['context'])
    used = [declaration, out / 'predeclaration-receipt.json']
    prior = {}
    for name in ['readiness.json', 'eligibility-results.json', 'eligibility-policy.json', 'manifest.json', 'coverage.json']:
        used.append(inp / name)
        prior[name] = json.loads((inp / name).read_text())
    checkpoint(out, 'Streaming normalized records under 1536 MiB address-space cap')
    groups = {n: defaultdict(set) for n in NAMES}
    tick_keys = {n: defaultdict(set) for n in NAMES}
    counts = defaultdict(Counter)
    rows_per_second = {n: Counter() for n in NAMES}
    trades = []
    norm = inp / 'normalized-records.jsonl'
    used.append(norm)
    nh = hashlib.sha256()
    with norm.open('rb') as f:
        for line in f:
            nh.update(line)
            r = json.loads(line)
            n, s, tick = r['feed'], r['source_epoch_second'], r['tick']
            counts[n]['normalized_rows'] += 1
            if r['exclusion']:
                counts[n]['excluded_' + r['exclusion']] += 1
                continue
            if not cstart <= s < cend or s != tick['time']:
                raise ValueError('Unexpected normalized context/time')
            counts[n]['context_rows'] += 1
            if start <= s < end:
                counts[n]['evaluation_rows'] += 1
            if n.endswith('_trades'):
                trades.append(r)
                continue
            rows_per_second[n][s] += 1
            tick_keys[n][s].add(json.dumps(tick, sort_keys=True, separators=(',', ':')))
            if n in QUOTES:
                flags = tick.get('tickAttribBidAsk', {})
                state = tuple(dec(tick[k]) for k in ['priceBid', 'priceAsk', 'sizeBid', 'sizeAsk']) + (flags.get('bidPastLow'), flags.get('askPastHigh'))
            else:
                state = dec(tick['price'])
            groups[n][s].add(state)
    keys = {n: sorted(g) for n, g in groups.items()}
    stats, summaries = {}, {n: {} for n in NAMES}
    with (out / 'source-second-audit.jsonl').open('w') as f:
        for n in NAMES:
            for interval, lo, hi in [('context', cstart, cend), ('evaluation', start, end)]:
                ss = [s for s in keys[n] if lo <= s < hi]
                stat = Counter(seconds=len(ss), rows=sum(rows_per_second[n][s] for s in ss))
                for s in ss:
                    states, full = groups[n][s], tick_keys[n][s]
                    stat['unique_states'] += len(states)
                    stat['duplicate_identical_state_rows'] += rows_per_second[n][s] - len(states)
                    stat['duplicate_identical_full_tick_rows'] += rows_per_second[n][s] - len(full)
                    stat['seconds_multiple_rows'] += rows_per_second[n][s] > 1
                    stat['seconds_multiple_states'] += len(states) > 1
                    stat['seconds_multiple_rows_only_one_state'] += rows_per_second[n][s] > 1 and len(states) == 1
                    if n in QUOTES:
                        pairs = {(x[0], x[1]) for x in states}
                        stat['seconds_multiple_price_pairs'] += len(pairs) > 1
                        stat['seconds_size_or_flag_only_variation'] += len(pairs) == 1 and len(states) > 1
                stats.setdefault(n, {})[interval] = dict(stat)
            for s in keys[n]:
                vals = groups[n][s]
                q = {'source_second': s, 'distinct_states': len(vals), 'rows': rows_per_second[n][s]}
                if n in QUOTES:
                    pairs = {(v[0], v[1]) for v in vals}
                    valid = all(all(x.is_finite() for x in v[:4]) and 0 < v[0] <= v[1] and min(v[2:4]) > 0 and v[4] is False and v[5] is False for v in vals)
                    q.update(valid=valid, ambiguous=len(pairs) > 1, distinct_price_pairs=len(pairs),
                             sizes_unambiguous=len({v[2:4] for v in vals}) == 1,
                             envelope={k: str(fn(v[i] for v in vals)) for k, i, fn in [('bid_min',0,min),('bid_max',0,max),('ask_min',1,min),('ask_max',1,max),('bid_size_min',2,min),('ask_size_min',3,min)]})
                else:
                    q.update(valid=all(v.is_finite() and v > 0 for v in vals), ambiguous=len(vals) != 1)
                summaries[n][s] = q
                f.write(json.dumps({'feed': n, **q}, sort_keys=True) + '\n')
    # Release the large row/state sets before sensitivity aggregation.
    del groups, tick_keys

    def select(n, t, age, lag=0):
        i = bisect.bisect_left(keys[n], t - lag) - 1
        if i < 0:
            return {'reasons': ['no_prior_observation'], 'pass': False}
        s = keys[n][i]
        q = dict(summaries[n][s])
        reasons = []
        if t - s > age:
            reasons.append('stale')
        if not q['valid']:
            reasons.append('invalid_price_size_or_flags' if n in QUOTES else 'invalid_index_value')
        if q['ambiguous']:
            reasons.append('ambiguous_source_second')
        q.update(reasons=reasons, age_seconds=t-s, **{'pass': not reasons})
        return q

    def decision(t, age=5, vage=60, skew=1, lag=0):
        qs = {n: select(n,t,vage if n in VIX else age,lag) for n in NAMES}
        times = [qs[n].get('source_second') for n in CORE]
        spread = max(times)-min(times) if all(s is not None for s in times) else None
        sync = spread is not None and spread <= skew
        pair_times = [qs[n].get('source_second') for n in [CALL,PUT]]
        pair_sync = all(s is not None for s in pair_times) and abs(pair_times[0]-pair_times[1]) <= skew
        env_ok = lambda n: not [r for r in qs[n]['reasons'] if not (n in QUOTES and r=='ambiguous_source_second')]
        point = sync and all(q['pass'] for q in qs.values())
        envelope = sync and all(env_ok(n) for n in NAMES)
        reasons = [f'{n}:{r}' for n,q in qs.items() for r in q['reasons']]
        if spread is not None and spread > skew:
            reasons.append('option_spx_hedge_skew_over_1s' if skew==1 else 'core_skew')
        d = {'decision_epoch': t, 'point': point, 'envelope': envelope,
             'core_envelope': sync and all(env_ok(n) for n in CORE),
             'core_source_skew_seconds': spread, 'reasons': reasons, 'inputs': qs,
             'components': {'option_pair_point_seconds': pair_sync and all(qs[n]['pass'] for n in [CALL,PUT]),
                            'option_pair_uncertainty_envelope_seconds': pair_sync and all(env_ok(n) for n in [CALL,PUT]),
                            'hedge_point_seconds': qs[ES]['pass'],
                            'all_index_inputs_seconds': all(qs[n]['pass'] for n in [SPX,*VIX])}}
        if d['components']['option_pair_uncertainty_envelope_seconds']:
            c,p = ({k:dec(v) for k,v in qs[n]['envelope'].items()} for n in [CALL,PUT])
            bounds = {'straddle_bid_lower':c['bid_min']+p['bid_min'], 'straddle_bid_upper':c['bid_max']+p['bid_max'],
                      'straddle_ask_lower':c['ask_min']+p['ask_min'], 'straddle_ask_upper':c['ask_max']+p['ask_max'],
                      'parity_lower':c['bid_min']-p['ask_max'], 'parity_upper':c['ask_max']-p['bid_min']}
            bounds['pessimistic_displayed_roundtrip'] = bounds['straddle_ask_upper']-bounds['straddle_bid_lower']
            bounds['parity_width'] = bounds['parity_upper']-bounds['parity_lower']
            bounds['straddle_ask_uncertainty_width'] = bounds['straddle_ask_upper']-bounds['straddle_ask_lower']
            d['bounds_points'] = {k:str(v) for k,v in bounds.items()}
        return d

    checkpoint(out, 'Source states aggregated; evaluating predeclared candidates')
    baseline = [decision(t) for t in range(start,end)]
    ex = Counter(r for d in baseline for r in d['reasons'])
    components = {k:sum(d['components'][k] for d in baseline) for k in baseline[0]['components']}
    actual = {'decision_count':len(baseline), 'eligible_synchronized_point_decisions':sum(d['point'] for d in baseline),
              'component_eligibility_counts':components, 'decision_exclusion_counts':dict(ex)}
    saved = prior['eligibility-results.json']
    reconciliation = {k:{'matches':v == saved[k], 'recomputed':v, 'prior':saved[k]} for k,v in actual.items()}
    coverage = prior['coverage.json']
    reconciliation['context_counts'] = {'matches': all(counts[f['feed']]['context_rows'] == f['counts']['context_records'] for f in coverage['feeds'])}
    manifest_entry = next(a for a in prior['manifest.json']['artifacts'] if Path(a['path']) == norm)
    reconciliation['normalized_manifest_hash'] = {'matches': nh.hexdigest()==manifest_entry['sha256'], 'sha256':nh.hexdigest(), 'expected':manifest_entry['sha256']}
    # Independent per-decision reconciliation, not just an aggregate zero.
    used.append(inp / 'eligibility-decisions.jsonl')
    differences = []
    with (inp / 'eligibility-decisions.jsonl').open() as f:
        num = 0
        for num, line in enumerate(f,1):
            old = json.loads(line)
            d = baseline[num-1] if num <= len(baseline) else None
            if d is None or old['decision_epoch'] != d['decision_epoch'] or old['eligible_point_inputs'] != d['point'] or sorted(old['reasons']) != sorted(d['reasons']):
                differences.append(num)
        if num != len(baseline): differences.append('row_count')
    reconciliation['per_decision'] = {'matches': not differences, 'rows':num, 'different_rows':differences}
    with (out / 'decisions.jsonl').open('w') as f:
        for d in baseline: f.write(json.dumps(d,sort_keys=True)+'\n')

    sensitivity=[]
    for age,vage,skew in itertools.product(config['sensitivity']['quote_spx_max_age_seconds'],config['sensitivity']['vix_max_age_seconds'],config['sensitivity']['core_max_skew_seconds']):
        ds = [decision(t,age,vage,skew) for t in range(start,end)]
        sensitivity.append({'quote_spx_max_age':age,'vix_max_age':vage,'core_max_skew':skew,'decisions':len(ds),
                            'points':sum(d['point'] for d in ds),'envelopes':sum(d['envelope'] for d in ds),'core_envelopes':sum(d['core_envelope'] for d in ds)})
    grids=[]
    for lag,step in [(0,s) for s in config['sensitivity']['grid_seconds']] + [(2,5)]:
        ds = baseline if lag==0 else [decision(t,lag=lag) for t in range(start,end)]
        phases=[]
        for phase in range(step):
            selected=ds[phase::step]
            phases.append({'phase':phase,'n':len(selected),'points':sum(d['point'] for d in selected),'envelopes':sum(d['envelope'] for d in selected)})
        grids.append({'lag_seconds':lag,'grid_seconds':step,'phase_results':phases,
                      'min_envelope_fraction':min(p['envelopes']/p['n'] for p in phases),
                      'max_envelope_fraction':max(p['envelopes']/p['n'] for p in phases),
                      'causal_candidate_adopted':False})
    trade_counts=Counter(); trade_details=[]
    for r in trades:
        t=r['source_epoch_second'];tick=r['tick']
        if not start<=t<end:continue
        flags=tick.get('tickAttribLast',{});positive=[];unknown=[]
        if 'unreported' not in flags or 'pastLimit' not in flags:unknown.append('missing_trade_flags')
        if flags.get('unreported'):positive.append('unreported')
        if flags.get('pastLimit'):positive.append('past_limit')
        if tick.get('specialConditions')=='f' and tick.get('exchange')=='CBOE':positive.append('complex_to_complex_COA_not_standalone')
        elif tick.get('specialConditions'):unknown.append('condition_not_allowlisted')
        if not all(dec(tick[k]).is_finite() and dec(tick[k])>0 for k in ['price','size']):positive.append('invalid_price_or_size')
        q=select(CALL if 'call' in r['feed'] else PUT,t,5)
        unknown.extend(q['reasons'])
        if q['pass'] and not dec(q['envelope']['bid_min'])<=dec(tick['price'])<=dec(q['envelope']['ask_max']):positive.append('outside_causal_quote')
        cls='ineligible_excluded' if positive else ('eligibility_unknown_excluded' if unknown else 'eligible_broker_history_print')
        trade_counts[cls]+=1
        trade_details.append({'feed':r['feed'],'source_second':t,'classification':cls,'positive_exclusions':positive,'unknown_exclusions':unknown,'raw_file':r['raw_file'],'callback_index':r['callback_index'],'tick_index':r['tick_index']})
    reconciliation['trade_classifications']={'matches':dict(trade_counts)==saved['trade_classifications'],'recomputed':dict(trade_counts),'prior':saved['trade_classifications']}
    result={'schema_version':1,'task':'Q2-T17','source_acceptance':'unaccepted','replay_ready':False,
            'scope':config['scope'],'intervals':{'evaluation':config['evaluation'],'context':config['context']},
            'predeclaration_sha256':receipt['sha256'],'reconciliation':reconciliation,'feed_row_exclusions':{n:dict(v) for n,v in counts.items()},'state_statistics':stats,
            'strict':actual,'envelopes':{'option_pair':components['option_pair_uncertainty_envelope_seconds'],'core':sum(d['core_envelope'] for d in baseline),'all_inputs':sum(d['envelope'] for d in baseline),'certified_causal_lower_bound':0},
            'age_distributions':{n:describe([d['inputs'][n]['age_seconds'] for d in baseline if 'age_seconds' in d['inputs'][n]]) for n in NAMES},
            'core_source_skew_distribution':describe([d['core_source_skew_seconds'] for d in baseline if d['core_source_skew_seconds'] is not None]),
            'bounds_distributions_points':{k:describe([dec(d['bounds_points'][k]) for d in baseline if 'bounds_points' in d]) for k in baseline[0].get('bounds_points',{})},
            'sensitivity':sensitivity,'grid_sensitivity':grids,'trade_details':trade_details,
            'limitations':['Source-time coverage is not receipt-time causality.','Observed-state envelopes do not bound unobserved/corrected/missing events or future fills.','No rate, forward, P&L, fill, price accuracy or strategy-validity inference.','The strict rules already collapse identical quote states; deduplication cannot repair genuine price ambiguity.']}
    save(out/'feasibility.json',result)
    hashes=[digest(p) for p in used if p!=norm]+[{'path':str(norm),'bytes':norm.stat().st_size,'sha256':nh.hexdigest()}]
    save(out/'audit-run.json',{'started_from_predeclaration':receipt,'completed_at':utc(),'elapsed_seconds':time.monotonic()-began,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'python':sys.version,'executable':sys.executable,'argv':sys.argv,'input_hashes':hashes,'seed':None,'numerical_threads':1,'checks':{'all_reconciliation_matches':all(x['matches'] for x in reconciliation.values())}})
    checkpoint(out,'Numerical audit complete; pricing documentation and handoff pending')
    print(json.dumps({'strict':actual,'envelopes':result['envelopes'],'reconciliation_ok':all(x['matches'] for x in reconciliation.values()),'elapsed_seconds':time.monotonic()-began}),flush=True)
    if not all(x['matches'] for x in reconciliation.values()):
        raise SystemExit('Artifact reconciliation mismatch; inspect before handoff')

if __name__=='__main__':
    main()
