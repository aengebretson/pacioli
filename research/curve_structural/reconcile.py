"""Reconcile produced research artifacts and immutable input hashes.

This is artifact bookkeeping and numerical-result reconciliation, not an
automated software test suite. It does not execute the model or fit parameters.
Run with: python3 -B research/curve_structural/reconcile.py
"""
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path('/home/andrew/luca-development/state/maintenance/vol-curve-20260930/structural/output')


def read(name):return json.loads((OUT/name).read_text())


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    checks=[]
    def check(label,ok,detail):checks.append({'check':label,'satisfied':bool(ok),'detail':detail})
    baseline=read('baseline-reproduction.json');comparison=read('chronological-comparison.json')
    validation=read('structural-validation.json');numerics=read('numerical-diagnostics.json')
    additional=read('additional-diagnostics.json');provenance=read('provenance.json')
    decl=read('predeclaration.json')
    check('embedded artifact identity',validation['baseline']==baseline and validation['comparison']==comparison and validation['numerical']==numerics and validation['additional_diagnostics']==additional,'primary sections equal their saved component artifacts')
    check('frozen predeclaration hash',digest(OUT/'predeclaration.json')==validation['predeclaration_sha256'],'declaration predates new scoring and is unchanged')
    check('two specifications only',len(comparison['fits'])==2 and additional['calibrations_performed']==0,'baseline audit reproduction plus exactly two candidate calibration specifications; supplementary work performs no fit')
    check('chronological boundary',max(decl['training_dates'])<min(decl['evaluation_dates']),'historical exploratory evaluation begins after training and saved baseline calibration')
    check('date counts',[comparison['summaries'][k]['evaluation']['dates_computed'] for k in comparison['summaries']]==[8,8,8],'all three models have eight computed evaluation dates; per-date records retained')
    check('baseline reproduction',all(v==0 for v in baseline['pricing_differences'].values()) and baseline['state_reproduction_difference']==0 and baseline['heldout_std_difference']==0,'saved state, original MC call/put/straddle and held-out residual SD match exactly')
    check('independent objective reproduction',abs(baseline['independent_objective_scan']['audit_rmse_difference'])<1e-12,'RMSE difference vs supplied audit '+str(baseline['independent_objective_scan']['audit_rmse_difference']))
    paths=[v['path_count'] for v in baseline['pricing']['checkpoints']]
    for mc in numerics['mc_replications']+additional['cross_horizon_mc']:paths += [v['path_count'] for v in mc['checkpoints']]
    check('path cap',max(paths)<=80000,{'maximum':max(paths)})
    check('numerical recurrence',max(abs(v['difference']) for v in numerics['recurrence'])<1e-14,{'max_absolute_difference':max(abs(v['difference']) for v in numerics['recurrence'])})
    check('one-period analytic reference',abs(additional['short_horizon_truncation_followup'][0]['black_straddle_difference'])<1e-9,'deterministic one-period Black comparison; this is a numerical calculation, not market validation')
    check('reported infeasible scenario',any(v['status']=='inadmissible' for v in numerics['parameter_sensitivity']),'1.1 innovation-coefficient scale violates physical stationarity and is retained')
    check('reported effective state boundary',additional['anchor_identification']['near_effective_boundary'],'positivity-boundary issue is retained despite optimizer success')
    check('source input hash reconciliation',all(digest(p)==info['sha256'] for p,info in provenance['input_files'].items()),{'input_files':len(provenance['input_files'])})
    check('pinned design digest',provenance['input_files']['/home/andrew/luca-development/control/planning/increments/Q2-I19.md']['sha256']=='21c8670a76e78f3a0c4a202bd4e95b6c87ae5dca44af7ebba3467c4058d961c5','matches dispatch')
    check('pinned source-design digest',provenance['input_files']['/home/andrew/luca-development/control/planning/tracks/VOL_CURVE_RESEARCH_20260930.md']['sha256']=='bdd0bbaf76b0423d735fb6f7661f8b13b95f7fea8327c0fb3a2d5e1ca4722499','matches dispatch')
    for p in (ROOT/'research/curve_structural').glob('*.py'):ast.parse(p.read_text(),filename=str(p))
    check('Python AST syntax',True,'all four research Python sources parsed; no bytecode produced')
    shell=subprocess.run(['bash','-n','research/curve_structural/run.sh','research/curve_structural/diagnose.sh'],cwd=ROOT,capture_output=True,text=True)
    check('shell syntax',shell.returncode==0,shell.stderr)
    tracked=subprocess.run(['git','diff','--quiet'],cwd=ROOT)
    staged=subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT)
    check('tracked baseline and index unchanged',tracked.returncode==0 and staged.returncode==0,'read-only Git inspection; no staging or commits')
    status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True)
    paths=[line[3:] for line in status.splitlines()]
    check('allowed source paths',all(p.startswith('research/curve_structural/') for p in paths),paths)
    (OUT/'CHANGED_FILES.txt').write_text('\n'.join(paths)+'\n')
    check('required narrative artifacts',all((OUT/n).is_file() for n in ['structural-validation-report.md','source-audit.json','INTERFACE_REQUEST.md']),'report, source audit and cross-scope proposal present')
    record={'schema_version':'luca.curve-structural.reconciliation.v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'status':'reconciled' if all(c['satisfied'] for c in checks) else 'requires_review','checks':checks,
            'stochastic_flags_not_erased':{'one_session_price_z':additional['cross_horizon_mc'][0]['straddle_z_vs_deterministic'],'252_session_parity_z':additional['cross_horizon_mc'][-1]['final']['put_call_parity_residual_z_score']},
            'automated_software_tests_run':False}
    (OUT/'artifact-reconciliation.json').write_text(json.dumps(record,indent=2)+'\n')
    provenance['source_files']={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'research/curve_structural').glob('*')) if p.is_file()}
    provenance['artifact_reconciliation_command']='python3 -B research/curve_structural/reconcile.py'
    provenance['public_source_audit_sha256']=digest(OUT/'source-audit.json')
    provenance['artifact_hashes']={n:digest(OUT/n) for n in ['predeclaration.json','structural-validation.json','baseline-reproduction.json','chronological-comparison.json','numerical-diagnostics.json','additional-diagnostics.json','input-inventory.json','states-and-joins.json','source-audit.json','structural-validation-report.md','artifact-reconciliation.json']}
    (OUT/'provenance.json').write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':record['status'],'checks':len(checks),'source_files':paths,'input_hashes_rechecked':len(provenance['input_files'])},indent=2))
    return 0 if record['status']=='reconciled' else 1


if __name__=='__main__':raise SystemExit(main())
