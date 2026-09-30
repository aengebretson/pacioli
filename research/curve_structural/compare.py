"""Q2-T19 bounded comparison. All generated artifacts stay in runtime output/.

Run through run.sh so the read-only ABI-compatible environment, one-thread
policy, bytecode prohibition and subprocess timeout are explicit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy.optimize import brentq

from luca_research.vrp.model import PhysicalDynamics, RiskPrices, cumulative_variance_premium, expected_variance_path, risk_neutral_dynamics
from luca_research.vrp.estimation import filter_physical_returns, summarize_filter_segment
from luca_research.vrp.pricing import EuropeanOptionInputs, MonteCarloPricingConfig, price_european_options_monte_carlo, option_pricing_result_asdict, _black_benchmark
from numerics import anchor_state, bounded_scan, curve, deterministic_price, expected_average, gaussian_transition_diagnostic, transform

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=Path('/home/andrew/luca-development/state/maintenance/vol-curve-20260930/structural')
REFERENCE=Path('/home/andrew/luca-development/state/maintenance/spx-trading-next-20260928/reference')
SAVED=Path('/home/andrew/luca-development/state/runs/Q2-T14-20260928171645-eee620/output/empirical-vrp.json')
AUDIT=RUNTIME.parent/'reference/fixed-parameter-objective-check.json'
REPLAY=Path('/home/andrew/vol-term-structure/data/replay-workers-20260929/qualify-session')
QUOTE_FILE=REFERENCE.parent/'event-reference/daily-quotes.csv'
PERIODS=np.array([6,21,63,126,252])
TERMS=['VIX9D','VIX','VIX3M','VIX6M','VIX1Y']
START=time.monotonic()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    tmp.replace(path)


class Run:
    def __init__(self,out):
        self.out=out
        self.inputs={}
        self.exclusions=[]
        self.commands=[]
        self.status('started bounded numerical batch')
        self.declaration=self.read(RUNTIME/'output/predeclaration.json')
        self.saved=self.read(SAVED)
        self.audit=self.read(AUDIT)
        self.physical=PhysicalDynamics(**self.saved['physical_estimation']['parameters'])
        self.risk=RiskPrices(**self.saved['pricing_calibration']['risk_prices'])
        self.h=self.saved['physical_estimation']['cutoff_state']['selected_h_next']
        self.option=EuropeanOptionInputs(**self.saved['option_pricing']['inputs'])
        self.p=risk_neutral_dynamics(self.physical,self.risk).persistence
        self.c=self.physical.innovation_intercept
        self.lower=self.physical.beta+self.physical.alpha*(self.physical.gamma1+self.risk.lambda1+0.5)**2
        self.upper=0.99999999

    def record(self,path,usage='read'):
        path=Path(path)
        key=str(path)
        if key not in self.inputs:
            self.inputs[key]={'sha256':sha(path),'bytes':path.stat().st_size,'usage':usage}
        return path

    def read(self,path):
        return json.loads(self.record(path).read_text())

    def status(self,phase):
        now=datetime.now(timezone.utc).isoformat()
        inbox=RUNTIME/'output/INBOX.md'
        msg=inbox.read_text() if inbox.exists() else 'No INBOX.md exists.'
        state={'task':'Q2-T19','status':'in_progress','phase':phase,'updated_at':now,
               'elapsed_batch_seconds':time.monotonic()-START,'inbox_content':msg,
               'scope':'research/curve_structural/ source; assigned runtime/output artifacts only',
               'verification':'numerical diagnostics, syntax and artifact reconciliation; no software tests'}
        save(RUNTIME/'output/STATUS.json',state)
        with (RUNTIME/'output/STATUS.md').open('a') as f: f.write(f'\n{now}: {phase}. Inbox: {msg.strip()}\n')
        print(phase,flush=True)

    def provenance(self):
        paths=[ROOT/'AGENTS.md',ROOT/'docs/DEVELOPMENT_WORKFLOW.md',ROOT/'research/requirements.lock',
               ROOT/'research/docs/DIRECT_VRP_MODEL.md',ROOT/'research/src/luca_research/expiry_forecast.py',
               ROOT/'research/examples/empirical_vrp.py',RUNTIME/'assignment.json',
               RUNTIME.parent/'reference/WORKER_POLICY.md',RUNTIME.parent/'reference/DEVELOPMENT_WORKFLOW.md',
               RUNTIME.parent/'reference/pricing-validation.md',SAVED.parent/'HANDOFF.md']
        paths+=list((ROOT/'research/src/luca_research/vrp').glob('*.py'))
        control=Path('/home/andrew/luca-development/control/planning')
        paths += [control/'tasks/Q2-T19.md',control/'increments/Q2-I19.md',control/'tracks/VOL_CURVE_RESEARCH_20260930.md',control/'approvals/A-VOL-CURVE-20260930-Q2-I19.json']
        for p in paths:self.record(p,'policy, source or inherited baseline evidence')
        pinned=SAVED.parent/'research-venv'
        self.record(pinned/'pyvenv.cfg','environment metadata; launcher ABI mismatch')
        for module in [np,scipy]:self.record(module.__file__,'loaded pinned dependency entrypoint')
        self.record(Path(sys.executable).resolve(),'existing compatible interpreter executable')
        save(self.out/'provenance.json',{'schema_version':'luca.curve-structural.provenance.v1',
          'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
          'input_files':self.inputs,'source_files':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'research/curve_structural').glob('*')) if p.is_file()},
          'command':sys.argv,'reproducible_command':'bash research/curve_structural/run.sh --output-dir '+str(self.out),
          'python':sys.version,'executable':sys.executable,'numpy':np.__version__,'scipy':scipy.__version__,
          'platform':platform.platform(),'environment':{k:os.environ.get(k) for k in ['PYTHONPATH','PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},
          'environment_exception':'Pinned venv bin/python resolves to host Python 3.12 and cannot import its cp311 packages. Existing Python 3.11.16 reads the original NumPy 2.4.6/SciPy 1.17.1 site-packages through PYTHONPATH. No environment files changed.',
          'seeds_and_assumptions':self.declaration,'sample_exclusions':self.exclusions,
          'elapsed_seconds':time.monotonic()-START,'automated_tests_run':False,'integration_status':'unintegrated_review_source',
          'public_source_audit':'see source-audit.json and structural-validation-report.md; documents not market-data acquisition'})

    def history(self):
        self.status('loading exact-date returns and VIX; no outcome scoring yet')
        self.closes={}
        with self.record(REFERENCE/'daily/index.csv').open(newline='') as f:
            for row in csv.reader(f):
                if len(row)!=6:raise ValueError('index schema mismatch')
                if row[1]!='spx-index':continue
                d=row[2];date.fromisoformat(d)
                if d in self.closes:raise ValueError('duplicate SPX date '+d)
                v=float(row[3])
                if not math.isfinite(v) or v<=0:raise ValueError('invalid SPX close')
                self.closes[d]={'date':d,'close':v,'row_hash':row[5]}
        self.vix={}
        manifest=self.read(REFERENCE/'vix/manifest.json')
        expected={x['symbol']:x['sha256'] for x in manifest['files'] if x.get('status')=='downloaded'}
        for term in TERMS:
            p=self.record(REFERENCE/'vix'/f'{term}_History.csv')
            if sha(p)!=expected[term]:raise ValueError('VIX manifest hash mismatch')
            series={}
            with p.open(newline='') as f:
                rows=csv.DictReader(f)
                if rows.fieldnames!=['DATE','OPEN','HIGH','LOW','CLOSE']:raise ValueError('VIX schema mismatch')
                for row in rows:
                    d=datetime.strptime(row['DATE'],'%m/%d/%Y').date().isoformat()
                    if d in series:raise ValueError('duplicate VIX date')
                    v=float(row['CLOSE'])
                    if not math.isfinite(v) or v<=0:raise ValueError('invalid VIX close')
                    series[d]=v
            self.vix[term]=series
        self.read(REFERENCE/'daily/manifest.json')
        self.record(REFERENCE/'README.md')
        self.record(REFERENCE/'spx-calendar.json','snapshot metadata; not certified listing or historical calendar')
        self.rows={}
        dates=sorted(set(self.declaration['training_dates']+self.declaration['evaluation_dates']+['2024-01-03']))
        for d in dates:
            missing=[t for t in TERMS if d not in self.vix[t]]
            if d not in self.closes or missing:
                self.exclusions.append({'date':d,'reason':'missing exact date','missing_vix':missing,'missing_spx':d not in self.closes});continue
            values,identity=self.returns(d)
            filtered=filter_physical_returns(values,self.physical,lambda1=self.risk.lambda1,particle_count=512,seed=29)
            self.rows[d]={'date':d,'observed':[self.vix[t][d] for t in TERMS],
               'state':{k:v for k,v in asdict(filtered).items() if k not in ['predictive_variances','standardized_residuals','log_likelihood_contributions']},
               'return_count':len(values),'return_identity_sha256':canonical(identity),
               'last_return_date':d,'first_return_date':identity[0]['return_date']}
            self.status('filtered frozen P through '+d)
        save(self.out/'states-and-joins.json',{'rows':self.rows,'exclusions':self.exclusions,'timing':'SPX close 16:00 and assumed VIX availability 16:15 America/New_York; no receipt-vintage proof'})

    def returns(self,end):
        rows=[self.closes[d] for d in sorted(self.closes) if '2019-12-02'<=d<=end]
        ret=[math.log(y['close'])-math.log(x['close']) for x,y in zip(rows[:-1],rows[1:],strict=True)]
        identities=[{'previous_date':x['date'],'previous_row_hash':x['row_hash'],'return_date':y['date'],'return_row_hash':y['row_hash']} for x,y in zip(rows[:-1],rows[1:],strict=True)]
        return ret,identities

    def baseline(self):
        self.status('reproducing saved January 2024 curve, state, payoff and independent scan')
        obs=np.array(self.rows['2024-01-03']['observed'])
        model=curve(self.h,self.p,self.c,PERIODS)
        objective=lambda p:float(np.mean((curve(self.h,p,self.c,PERIODS)-obs)**2))
        scan=bounded_scan(objective,self.lower,self.upper)
        scan['lambda2']=math.sqrt((scan['pQ']-self.lower)/self.physical.rho)-self.physical.gamma2
        scan['audit_pQ_difference']=scan['pQ']-self.audit['best_pQ']
        scan['audit_rmse_difference']=scan['rmse_vix_points']-self.audit['best_rmse_vix_points']
        mc=price_european_options_monte_carlo(self.physical,self.risk,h_next=self.h,inputs=self.option,config=MonteCarloPricingConfig(path_counts=(20000,80000),seed=101))
        computed=option_pricing_result_asdict(mc)
        ret,_=self.returns('2024-01-03')
        filtered=filter_physical_returns(ret,self.physical,lambda1=self.risk.lambda1,particle_count=512,seed=29)
        held=summarize_filter_segment(filtered,ret,start_index=776,end_index_exclusive=1026)
        out={'observed_vix':obs.tolist(),'saved_state_curve':model.tolist(),'rmse_vix_points':math.sqrt(objective(self.p)),
             'pQ':self.p,'lambda2':self.risk.lambda2,'independent_objective_scan':scan,
             'baseline_source_assumptions':self.saved['option_pricing']['contract_and_market_input_provenance'],
             'baseline_source_status':'unintegrated, not accepted pricing; January 2024 illustration, not September 2026 replay',
             'state_reproduction_difference':filtered.h_next_mean-self.h,
             'heldout_2023_diagnostics':held,'heldout_std_difference':held['standardized_residual_std_ddof0']-self.saved['physical_estimation']['heldout_diagnostics']['standardized_residual_std_ddof0'],
             'pricing':computed,'pricing_differences':{x:computed['final'][x]['value']-self.saved['option_pricing']['final'][x]['value'] for x in ['call','put','straddle']},
             'variance_premium':asdict(cumulative_variance_premium(self.h,21,self.physical,self.risk)),
             'physical_parameters_refitted':False,'physical_optimizer_reproduction':'not rerun; saved physical parameters used as requested'}
        save(self.out/'baseline-reproduction.json',out)
        return out

    def comparison(self):
        self.status('two predeclared pooled scalar calibrations; train-only objectives')
        train=[self.rows[d] for d in self.declaration['training_dates'] if d in self.rows]
        if not train:raise ValueError('no training dates')
        obs=np.array([r['observed'] for r in train]); hs=np.array([r['state']['h_next_mean'] for r in train])
        fits={}
        for name in ['pooled_return_state','pooled_vix_anchor']:
            def objective(p):
                states=hs if name=='pooled_return_state' else anchor_state(obs[:,1],p,self.c)
                if np.any(states<=0):return math.inf
                residual=curve(states,p,self.c,PERIODS)-obs
                if name=='pooled_vix_anchor':residual=residual[:,[0,2,3,4]]
                return float(np.mean(residual**2))
            def cp(i,p,value):
                save(self.out/(name+'-checkpoint.json'),{'grid_index':i,'pQ':p,'objective':value if math.isfinite(value) else None,'elapsed_seconds':time.monotonic()-START})
            # Entire subprocess also has a 30-minute timeout; each fit has an alarm.
            signal.alarm(1800)
            fit=bounded_scan(objective,self.lower,self.upper,checkpoint=cp)
            signal.alarm(0)
            fit['lambda2']=math.sqrt((fit['pQ']-self.lower)/self.physical.rho)-self.physical.gamma2
            fit['equivalent_negative_branch_lambda2']=-2*self.physical.gamma2-fit['lambda2']
            fit['training_dates']=[r['date'] for r in train]
            fit['fitted_parameter_count']=1
            fit['conditional_state']=(name=='pooled_vix_anchor')
            # Save fit before evaluating any later-date outcome.
            save(self.out/(name+'-fit.json'),fit);fits[name]=fit
            self.status('saved training fit '+name+' before evaluation')
        models={'saved_jan2024':self.p,**{k:v['pQ'] for k,v in fits.items()}}
        records=[]
        for name,p in models.items():
            for partition,dates in [('training',self.declaration['training_dates']),('evaluation',self.declaration['evaluation_dates']),('illustration',['2024-01-03'])]:
                for d in dates:
                    if d not in self.rows:
                        records.append({'model':name,'date':d,'partition':partition,'status':'missing_input'});continue
                    row=self.rows[d];y=np.array(row['observed']);h=row['state']['h_next_mean']
                    if name=='pooled_vix_anchor':h=float(anchor_state(y[1],p,self.c))
                    record={'model':name,'date':d,'partition':partition,'h_next':h,'pQ':p,'observed':y.tolist(),
                            'state_ratio_to_return_filter':h/row['state']['h_next_mean'],
                            'same_date_vix_anchor_used':name=='pooled_vix_anchor'}
                    if h<=0:
                        record.update(status='infeasible_nonpositive_anchor_state');records.append(record);continue
                    prediction=curve(h,p,self.c,PERIODS);res=y-prediction
                    record.update(status='computed',predicted=prediction.tolist(),residual_observed_minus_model=res.tolist())
                    records.append(record)
        summaries={}
        for name in models:
            summaries[name]={}
            for partition in ['training','evaluation','illustration']:
                selected=[r for r in records if r['model']==name and r['partition']==partition]
                good=[r for r in selected if r['status']=='computed']
                if not good:
                    summaries[name][partition]={'dates_failed':len(selected),'dates_computed':0};continue
                res=np.array([r['residual_observed_minus_model'] for r in good])
                summaries[name][partition]={'dates_computed':len(good),'dates_failed':len(selected)-len(good),
                  'five_tenor_rmse':float(np.sqrt(np.mean(res**2))),
                  'near_two_tenor_rmse':float(np.sqrt(np.mean(res[:,:2]**2))),
                  'common_four_tenor_rmse':float(np.sqrt(np.mean(res[:,[0,2,3,4]]**2))),
                  'vix9d_rmse':float(np.sqrt(np.mean(res[:,0]**2))),
                  'bias_by_tenor':res.mean(axis=0).tolist(),'rmse_by_tenor':np.sqrt(np.mean(res**2,axis=0)).tolist(),
                  'anchor_included_metrics_not_comparable':name=='pooled_vix_anchor'}
        result={'fits':fits,'records':records,'summaries':summaries,'evaluation_claim':'chronological exploratory conditional curve comparison; VIX anchor model uses same-date VIX and is not a forecast',
                'joint_likelihood':'not estimated; two implemented staged specifications completed. Physical parameter uncertainty and paper measurement-error likelihood remain unimplemented.'}
        save(self.out/'chronological-comparison.json',result)
        return result

    def sensitivity(self):
        self.status('deterministic and Monte Carlo numerical diagnostics')
        p=self.physical;r=self.risk;h=self.h
        unit=replace(self.option,contract_multiplier=1.0)
        recurrence=[]
        for horizon in [1,6,21,63,252]:
            direct=math.fsum(expected_variance_path(h,horizon,p,measure='Q',risk_prices=r))
            closed=float(expected_average(h,self.p,self.c,[horizon])[0]*horizon)
            recurrence.append({'horizon':horizon,'recurrence_total':direct,'closed_total':closed,'difference':direct-closed,
                               'transform_M0_error':abs(transform(0,horizon,h,p,r)-1),'transform_M1_error':abs(transform(1,horizon,h,p,r)-1)})
        deterministic=[]
        for horizon in [1,6,21,63,252]:
            for cutoff in [100,200,400,800]:
                value=deterministic_price(p,r,h,replace(unit,horizon_trading_days=horizon),cutoff)
                value['horizon']=horizon;deterministic.append(value)
            self.status('completed deterministic inversion horizon '+str(horizon))
        mc=[]
        for seed in [101,102,103]:
            value=option_pricing_result_asdict(price_european_options_monte_carlo(p,r,h_next=h,inputs=unit,config=MonteCarloPricingConfig(path_counts=(20000,40000,80000),seed=seed)))
            target=[x for x in deterministic if x['horizon']==21 and x['cutoff']==800][0]['straddle']
            value['deterministic_straddle_z']=(value['final']['straddle']['value']-target)/value['final']['straddle']['standard_error']
            mc.append(value)
        filter_results=[];ret,_=self.returns('2024-01-03')
        for particles in [128,512,2048]:
            for seed in [29,30,31]:
                f=filter_physical_returns(ret,p,lambda1=r.lambda1,particle_count=particles,seed=seed)
                pricing=deterministic_price(p,r,f.h_next_mean,unit)
                filter_results.append({'particles':particles,'seed':seed,'h_mean':f.h_next_mean,'h_p05':f.h_next_p05,'h_p95':f.h_next_p95,
                   'average_log_likelihood':f.average_log_likelihood,'straddle':pricing['straddle'],'vix_curve':curve(f.h_next_mean,self.p,self.c,PERIODS).tolist()})
        states=[]
        savedstate=self.saved['physical_estimation']['cutoff_state']
        for label,key in [('p05','p05'),('median','median'),('mean','selected_h_next'),('p95','p95')]:
            hs=savedstate[key]
            states.append({'state_label':label,'h':hs,'curve':curve(hs,self.p,self.c,PERIODS).tolist(),
                           'price':deterministic_price(p,r,hs,unit)})
        variants=[]
        for key in ['lambda1','lambda2']:
            for offset in [-1,1]:
                variants.append((f'{key}{offset:+d}',p,replace(r,**{key:getattr(r,key)+offset})))
        for scale in [0.9,1.1]:
            try:pp=replace(p,omega=p.omega*scale,alpha=p.alpha*scale,rho=p.rho*scale)
            except ValueError as exc:
                variants.append((f'innovation_scale_{scale}',str(exc),r));continue
            variants.append((f'innovation_scale_{scale}',pp,r))
        parameters=[]
        for label,pp,rr in variants:
            try:
                if isinstance(pp,str):raise ValueError(pp)
                q=risk_neutral_dynamics(pp,rr)
                parameters.append({'label':label,'status':'computed','pP':pp.persistence,'pQ':q.persistence,
                  'curve':curve(h,q.persistence,pp.innovation_intercept,PERIODS).tolist(),
                  'price':deterministic_price(pp,rr,h,unit),'refitted':False})
            except ValueError as exc:parameters.append({'label':label,'status':'inadmissible','reason':str(exc),'refitted':False})
        calendars=[]
        maps={'baseline_integer':PERIODS,'paper_fractional':[6.3,21,63,126,252],
              'constant_calendar_252_365':np.array([9,30,93,184,366])*252/365}
        obs=np.array(self.rows['2024-01-03']['observed'])
        for label,periods in maps.items():
            prediction=curve(h,self.p,self.c,periods)
            calendars.append({'label':label,'periods':list(map(float,periods)),'curve':prediction.tolist(),
                              'rmse':float(np.sqrt(np.mean((obs-prediction)**2))),'refitted':False})
        counts=[];pred=[]
        origin=date(2024,1,3)
        for days in [9,30,93,184,366]:
            end=(origin+timedelta(days=days)).isoformat()
            n=sum('2024-01-03'<d<=end for d in self.closes)
            counts.append(n)
            w=math.fsum(expected_variance_path(h,n,p,measure='Q',risk_prices=r))
            pred.append(100*math.sqrt(w/(days/365)))
        calendars.append({'label':'available_close_session_count_calendar_annualization','periods':counts,'curve':pred,
                          'rmse':float(np.sqrt(np.mean((obs-pred)**2))),'refitted':False,
                          'limitation':'retrospective close-date proxy, not verified exchange calendar; no fractional intraday or nontrading-day allocation'})
        carry=[]
        for label,inputs in [('baseline',unit),('forward_minus_1pct',replace(unit,forward=unit.forward*.99)),('forward_plus_1pct',replace(unit,forward=unit.forward*1.01)),('discount_0_995',replace(unit,discount_factor=.995)),('20_sessions',replace(unit,horizon_trading_days=20)),('22_sessions',replace(unit,horizon_trading_days=22))]:
            carry.append({'label':label,'classification':'hypothetical_sensitivity_not_observed_inputs','inputs':asdict(inputs),'price':deterministic_price(p,r,h,inputs)})
        results={'units':'index points (multiplier=1), variance decimal per trading interval','recurrence':recurrence,'gaussian_quadrature':gaussian_transition_diagnostic(p,r,h),
          'deterministic_inversion':deterministic,'mc_replications':mc,'filter_particle_seed_sensitivity':filter_results,
          'state_quantile_sensitivity':states,'parameter_sensitivity':parameters,'calendar_sensitivity':calendars,'carry_and_horizon_sensitivity':carry,
          'uncertainty_scope':'MC intervals only conditional sampling error. State-quantile and local parameter perturbations are sensitivities, not total fair-value intervals or parameter confidence intervals.',
          'deterministic_derivation':'Two-Gaussian affine recursion derived in numerics.py; finite-cutoff Fourier integration is independent of simulation, put obtained by parity. Cutoff sensitivity is not a rigorous tail bound.'}
        save(self.out/'numerical-diagnostics.json',results)
        return results

    def inventory(self):
        self.status('streaming existing option schema and inspecting replay qualification metadata')
        contracts={}
        with self.record(REFERENCE/'daily/contracts.csv').open(newline='') as f:
            for row in csv.reader(f):
                if len(row)!=6:raise ValueError('contract schema mismatch')
                if row[0] in contracts:raise ValueError('duplicate contract id')
                contracts[row[0]]=row
        counts=Counter();flags=Counter();sample=[];dates=Counter();exact=[]
        with self.record(QUOTE_FILE,'streamed full schema/flags/date/contract-identity inventory; no executable quote scoring').open(newline='') as f:
            for row in csv.reader(f):
                counts['rows']+=1
                if len(row)!=11:counts['wrong_width']+=1;continue
                counts['width_11']+=1;dates[row[2]]+=1
                flags.update(json.loads(row[8]))
                c=contracts.get(row[1])
                if c is None:counts['unmatched_contract']+=1;continue
                counts['matched_contract']+=1
                # Keep only bounded illustrative identity samples, never copy raw dataset.
                if len(sample)<2:sample.append({'instrument':row[1],'date':row[2],'contract':c,'flags':json.loads(row[8])})
                if row[2]=='2024-01-03' and c[3]=='2024-02-02' and float(c[4])==4705:
                    exact.append({'instrument':row[1],'date':row[2],'contract':c,'flags':json.loads(row[8]),'bid':float(row[3]),'ask':float(row[4])})
        summaries={}
        for filename in ['readiness.json','eligibility-policy.json','eligibility-results.json','pricing-input-status.json','existing-rate-evidence-check.json','manifest.json']:
            value=self.read(REPLAY/filename)
            summaries[filename]={'top_level_keys':list(value),'bytes':(REPLAY/filename).stat().st_size}
            if filename in ['readiness.json','existing-rate-evidence-check.json','pricing-input-status.json']:summaries[filename]['evidence']=value
        self.record(REPLAY/'REPORT.md','read prior completed qualification; no replay recomputation')
        p=self.record(REPLAY/'normalized-records.jsonl','first record schema inspected; full file streamed for hash only')
        with p.open() as f:normalized=json.loads(next(f))
        result={'option_quote_schema':['dataset_id','instrument_id','observation_date','bid','ask','vendor_iv','vendor_delta','boolean_field_not_independently_qualified','flags_json','source_hashes_json','row_hash'],
                'field_interpretation':'first fields cross-checked against contracts and values; IV/delta/boolean semantics are unverified and unused',
                'counts':dict(counts),'flags':dict(flags),'date_min':min(dates),'date_max':max(dates),
                'january3_rows':dates['2024-01-03'],'bounded_identity_samples':sample,'exact_illustrative_contract_rows':exact,
                'actual_option_validation':'not performed: daily clocks, historical listing and settlement, forward and discount unverified; matches alone do not permit synchronized price scoring',
                'replay_metadata':summaries,'normalized_schema_keys':list(normalized),
                'separate_replay':'September 25 2026 evaluation [14:00,14:30) UTC; reported strict 0/1800; October SPXW, not January illustration',
                'replay_recomputed':False,'raw_data_modified':False}
        save(self.out/'input-inventory.json',result)
        return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=RUNTIME/'output')
    args=parser.parse_args()
    out=args.output_dir.resolve()
    if out!=RUNTIME/'output' and RUNTIME/'output' not in out.parents:
        raise ValueError('generated data must stay inside assigned runtime output/')
    out.mkdir(parents=True,exist_ok=True)
    run=Run(out)
    try:
        run.history()
        baseline=run.baseline()
        comparison=run.comparison()
        numerical=run.sensitivity()
        inventory=run.inventory()
        result={'schema_version':'luca.curve-structural.validation.v1','task':'Q2-T19','status':'completed_exploratory_diagnostics_not_accepted_pricing',
                'predeclaration_sha256':sha(RUNTIME/'output/predeclaration.json'),'baseline':baseline,'comparison':comparison,
                'numerical':numerical,'inventory_artifact':'input-inventory.json','elapsed_seconds':time.monotonic()-START,
                'automated_tests_run':False,'candidate_calibrations_completed':2,'max_mc_paths':80000,
                'missing':['full joint physical/VIX likelihood and parameter uncertainty','historical source-vintage and exact time conventions','validated actual option/forward/discount/settlement comparison','Greek and event-repricing validation','genuinely unseen prospective evaluation']}
        save(out/'structural-validation.json',result)
        run.status('numerical batch complete; report and handoff preparation')
    except Exception as exc:
        save(out/'batch-failure.json',{'type':type(exc).__name__,'message':str(exc),'elapsed_seconds':time.monotonic()-START})
        raise
    finally:run.provenance()


if __name__=='__main__':main()
