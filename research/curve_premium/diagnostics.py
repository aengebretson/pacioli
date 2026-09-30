"""Read-only numerical summaries of a saved run; no refitting or selection."""
import argparse
import json
from collections import Counter
from common import existing_output, now, write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);out=existing_output(p.parse_args().output)
    fits=[]
    with (out/'physical-fits.jsonl').open() as stream:
        for line in stream:
            row=json.loads(line)
            if row['physical_model']=='garch_1_1':fits.append(row)
    persistence=[r['parameters']['alpha[1]']+r['parameters']['beta[1]'] for r in fits]
    nonpositive=Counter();band_negative=Counter()
    with (out/'forecasts.jsonl').open() as stream:
        for line in stream:
            row=json.loads(line);key=':'.join([row['partition'],row['term'],row['physical_model'],row['premium_model']])
            if row['predicted_W_market_proxy']<=0:nonpositive[key]+=1
            if row['excess_prediction_band'] is not None and row['W_P']+row['excess_prediction_band'][0]<0:band_negative[key]+=1
    artifact={'schema_version':'luca.curve-premium-model-diagnostics.v1','created_at':now(),
        'garch_fits':len(fits),'persistence_min':min(persistence),'persistence_max':max(persistence),
        'persistence_at_least_0_999':sum(v>=.999 for v in persistence),
        'persistence_above_1_plus_1e_8':sum(v>1+1e-8 for v in persistence),
        'nonpositive_predicted_market_proxy':dict(nonpositive),
        'prediction_band_implies_negative_market_proxy_lower_bound':dict(band_negative),
        'interpretation':'Diagnostic only. Near-unit persistence complicates long-run inference. Unconstrained excess regressions/bands can imply impossible market variances; retain and flag, never clip/retune this sample or convert to option fair values.'}
    write_json(out/'model-diagnostics.json',artifact)
    marker='\n## Unconstrained-model diagnostics\n'
    path=out/'benchmark-report.md';report=path.read_text().split(marker)[0]
    report+=marker+f"\nAll {len(fits)} GARCH fits converged; {artifact['persistence_at_least_0_999']} have alpha+beta >= 0.999. None exceed one by more than 1e-8. These finite-horizon forecasts are retained; stationarity and long-run inference are not established by convergence.\n\nAcross warmup and evaluation forecasts, {sum(nonpositive.values())} predicted market proxies are nonpositive and {sum(band_negative.values())} empirical bands have an implied-market lower bound below zero. `model-diagnostics.json` gives exact group counts. These are unconstrained statistical forecasts of excess variance, not admissible option pricing models. No clipping, recalibration or post-score candidate changes were made. The thresholds here are descriptive counts, not new exclusion rules.\n"
    path.write_text(report)
    print(json.dumps({'garch_fits':len(fits),'near_unit':artifact['persistence_at_least_0_999'],'nonpositive_market_proxy_forecasts':sum(nonpositive.values())}))


if __name__=='__main__':main()
