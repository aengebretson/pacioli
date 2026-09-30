"""Reconcile actual saved run artifacts, chronology and arithmetic; no fixtures."""
from __future__ import annotations
import argparse
import json
import math
import statistics
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from common import canonical_hash, checkpoint, digest, existing_output, now, write_json


def rows(path):
    with path.open() as stream:
        for line in stream:yield json.loads(line)


def keyed(path):
    result={}
    for row in rows(path):
        if row['id'] in result:raise ValueError(f'duplicate ID in {path.name}')
        result[row['id']]=row
    return result


def close(a,b):
    if not math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-14):
        raise ValueError(f'Numerical reconciliation failed: {a} versus {b}')


def require(condition,message):
    if not condition:raise ValueError(message)


def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',required=True);p.add_argument('--forecast-only',action='store_true');args=p.parse_args()
    out=existing_output(args.output)
    seal=json.loads((out/'forecast-seal.json').read_text());spec=json.loads((out/'predeclaration.json').read_text())
    supplied = [args.reference / 'daily/index.csv'] + sorted((args.reference / 'vix').glob('*_History.csv'))
    require({str(p.resolve()) for p in supplied} == {str(Path(p).resolve()) for p in seal['input_sha256']}, 'reference paths differ from forecast inputs')
    schemas=json.loads(Path(__file__).with_name('schemas.json').read_text())['$defs']
    for name,sha in seal['artifacts_sha256'].items():require(digest(out/name)==sha,f'seal changed: {name}')
    for name,sha in seal['input_sha256'].items():require(digest(name)==sha,f'input changed: {name}')
    require(digest(Path(__file__).with_name('predeclare.py'))==spec['source_sha256'],'declaration source changed')
    require(spec['declared_at']<seal['sealed_at'],'declaration not earlier than seal')
    forecasts=keyed(out/'forecasts.jsonl');fits=keyed(out/'fit-partitions.jsonl');observations=keyed(out/'observations.jsonl');physical=keyed(out/'physical-fits.jsonl')
    require(set(forecasts)==set(fits),'forecast and fit IDs differ')
    checked=Counter()
    for fid,f in forecasts.items():
        part=fits[fid]
        require(set(schemas['forecast']['required'])<=set(f),'forecast required fields absent')
        require(set(schemas['fit']['required'])<=set(part),'fit required fields absent')
        old=[observations[k] for k in part['training_observation_ids']]
        require(all(r['origin']<f['origin'] and r['term']==f['term'] and r['physical_model']==f['physical_model'] for r in old),'training leakage or mismatched study')
        require([r['origin'] for r in old]==sorted(set(r['origin'] for r in old)),'fit rows not unique and ordered')
        require(old[0]['origin']==part['training_first_date'] and old[-1]['origin']==part['training_last_date'],'partition bounds mismatch')
        require(canonical_hash(old)==part['training_sha256'],'training row hash mismatch')
        require(spec['premium_min_observations']<=len(old)<=spec['premium_fit_observations'],'training count mismatch')
        ids=part['interval_error_forecast_ids']
        require(len(ids)==f['prediction_band_error_count'],'band count mismatch')
        require(all(forecasts[k]['origin']<f['origin'] and forecasts[k]['term']==f['term'] and forecasts[k]['physical_model']==f['physical_model'] and forecasts[k]['premium_model']==f['premium_model'] for k in ids),'interval lookahead or cross-group errors')
        ph=physical[part['physical_fit_id']]
        require(ph['last_return_end_date']==f['origin'],'physical cutoff mismatch')
        close(math.fsum(ph['forecast_variances'][:f['forecast_intervals']]),f['W_P'])
        require(str(date.fromisoformat(f['origin'])+timedelta(days=f['horizon_calendar_days']))==f['horizon_end'],'horizon mismatch')
        close(f['tau_act365'],f['horizon_calendar_days']/365)
        close(f['predicted_W_market_proxy'],f['W_P']+f['predicted_normal_excess'])
        y = [r['observed_excess_annualized'] for r in old]
        if f['premium_model'] == 'trailing_mean':
            predicted = statistics.fmean(y)
        elif f['premium_model'] == 'trailing_median':
            predicted = statistics.median(y)
        else:
            beta = part['coefficients']
            predicted = beta[0] + beta[1] * (f['W_P']/f['tau_act365']-part['predictor_train_center'])/part['predictor_train_scale']
        close(predicted*f['tau_act365'], f['predicted_normal_excess'])
        if len(ids) >= 63:
            empirical = sorted((observations[k.rsplit(':',1)[0]]['observed_excess']-forecasts[k]['predicted_normal_excess'])/forecasts[k]['tau_act365'] for k in ids)
            require(f['excess_prediction_band'] is not None, 'missing band')
            for q, bound in zip([0.05, 0.95], f['excess_prediction_band']):
                index = q*(len(empirical)-1)
                low, high = math.floor(index), math.ceil(index)
                quantile = empirical[low] + (index-low)*(empirical[high]-empirical[low])
                close((predicted+quantile)*f['tau_act365'], bound)
        else:
            require(f['excess_prediction_band'] is None, 'band before sufficient history')
        obs=observations[fid.rsplit(':',1)[0]]
        close(obs['observed_excess'],obs['W_market']-obs['W_P'])
        checked['forecasts']+=1;checked['training_references']+=len(old);checked['interval_references']+=len(ids)
    require(checked['forecasts']==seal['forecasts'],'sealed count mismatch')
    if not args.forecast_only:
        result=json.loads((out/'benchmark-result.json').read_text())
        require(set(schemas['result']['required'])<=set(result),'result required fields absent')
        require(result['created_at']>seal['sealed_at'],'outcomes scored before seal')
        require(result['forecast_seal_sha256']==digest(out/'forecast-seal.json'),'result seal reference differs')
        seen=set();counts=Counter();nonoverlap=Counter()
        for row in rows(out/'scored-observations.jsonl'):
            require(row['id'] not in seen,'duplicate scored forecast');seen.add(row['id'])
            f=forecasts[row['id']]
            require(all(row[k]==v for k,v in f.items()),'scoring revised forecast')
            close(row['residual'],row['W_market']-row['W_P']-row['predicted_normal_excess'])
            require(f['partition']=='exploratory_evaluation','warmup scored')
            require(row['horizon_end']<=spec['partitions']['outcome_last_date'],'right censor violated')
            key=(row['term'],row['physical_model'],row['premium_model']);counts[key]+=1
            nonoverlap[key]+=row['nonoverlap_origin']
        require(len(seen)==result['scored_records'],'scored count differs')
        require(seen=={k for k,v in forecasts.items() if v['partition']=='exploratory_evaluation'},'missing evaluation forecast')
        for term,schedule in result['nonoverlap_schedules'].items():
            days=spec['terms'][term]
            require(all(date.fromisoformat(b)>=date.fromisoformat(a)+timedelta(days=days) for a,b in zip(schedule,schedule[1:])),'overlapping primary returns')
        for g in result['candidate_groups']:
            key=(g['term'],g['physical_model'],g['premium_model'])
            require(counts[key]==g['daily_overlapping_descriptive']['residual']['n'],'summary count mismatch')
            require(nonoverlap[key]==g['nonoverlapping_primary']['residual']['n'],'primary summary count mismatch')
        checked['scored_records']=len(seen);checked['candidate_groups']=len(counts)
    artifact={'schema_version':'luca.curve-premium-reconciliation.v1','created_at':now(),'stage':'forecast_only' if args.forecast_only else 'full_artifacts','checks':dict(checked),'status':'reconciled','software_tests_run':False,'scope':'Actual artifact hashes, required fields, saved chronology, partitions, arithmetic and non-overlap. Not full JSON Schema validation, software testing or economic validation.'}
    name='forecast-reconciliation.json' if args.forecast_only else 'artifact-reconciliation.json'
    write_json(out/name,artifact);checkpoint(out,'Artifact reconciliation complete',**dict(checked))


if __name__=='__main__':main()
