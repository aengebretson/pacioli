"""Additional bounded diagnostics of saved fits; performs no calibration.

Run: bash research/curve_structural/diagnose.sh
"""
from dataclasses import asdict,replace
import json
import math
from pathlib import Path
import time
import numpy as np
from scipy.optimize import brentq
from compare import RUNTIME,Run,PERIODS,save,sha
from numerics import anchor_state,curve,deterministic_price,transform
from luca_research.vrp.pricing import MonteCarloPricingConfig,price_european_options_monte_carlo,option_pricing_result_asdict,_black_benchmark


def main():
    started=time.monotonic();out=RUNTIME/'output';run=Run(out)
    comparison=json.loads((out/'chronological-comparison.json').read_text())
    states=json.loads((out/'states-and-joins.json').read_text())['rows']
    fit=comparison['fits']['pooled_vix_anchor'];train=fit['training_dates']
    minimum=min(train,key=lambda d:states[d]['observed'][1])
    min_vix=states[minimum]['observed'][1]
    cap=brentq(lambda p:float(anchor_state(min_vix,p,run.c)),run.lower,run.upper,xtol=1e-14)
    boundary={'constraining_training_date':minimum,'minimum_training_vix':min_vix,
      'effective_positive_state_upper_pQ_exclusive':cap,'fitted_pQ':fit['pQ'],
      'distance_to_effective_bound':cap-fit['pQ'],'near_effective_boundary':cap-fit['pQ']<1e-5,
      'minimum_fitted_training_state':float(anchor_state(min_vix,fit['pQ'],run.c)),
      'interpretation':'near_boundary in original fit refers only to outer stationarity bounds; positivity constraint is active. Infimum is at excluded zero-state boundary; optimizer success is not a well identified interior optimum.'}
    # Local Jacobian uses log(h),pQ coordinates: rank/conditioning diagnostic,
    # not standard errors or permission to fit a second parameter.
    eps=1e-5
    h,p=run.h,run.p
    jh=(curve(h*math.exp(eps),p,run.c,PERIODS)-curve(h*math.exp(-eps),p,run.c,PERIODS))/(2*eps)
    jp=(curve(h,p+eps,run.c,PERIODS)-curve(h,p-eps,run.c,PERIODS))/(2*eps)
    jac=np.stack([jh,jp],axis=1);singular=np.linalg.svd(jac,compute_uv=False)
    ident={'coordinates':['log(h)','pQ'],'jacobian_vix_points':jac.tolist(),'singular_values':singular.tolist(),
      'condition_number':float(singular.max()/singular.min()),'column_cosine':float(np.dot(jh,jp)/np.linalg.norm(jh)/np.linalg.norm(jp)),
      'lambda2_to_pQ_derivative':2*run.physical.rho*(run.physical.gamma2+run.risk.lambda2),
      'meaning':'local shape sensitivities with frozen physical coefficients; no extra parameter fitted, no sampling/parameter uncertainty inferred'}
    # New unresolved concern from first calculation: 1-session cutoff 400→800
    # moved 0.00275 point. Resolve by bounded 1600 endpoint and exact lognormal.
    run.status('resolving short-horizon Fourier truncation and feasible-bound diagnostic; no new fits')
    unit=replace(run.option,contract_multiplier=1.)
    short=[]
    for horizon in [1,6,21]:
        inputs=replace(unit,horizon_trading_days=horizon)
        p800=deterministic_price(run.physical,run.risk,h,inputs,800,tolerance=1e-10)
        p1600=deterministic_price(run.physical,run.risk,h,inputs,1600,tolerance=1e-10)
        row={'horizon':horizon,'cutoff800':p800,'cutoff1600':p1600,'straddle_difference':p1600['straddle']-p800['straddle']}
        if horizon==1:
            black=_black_benchmark(inputs,h)
            row.update(exact_one_period_black=black,black_straddle_difference=p1600['straddle']-black['straddle'])
        short.append(row)
    # Cross-horizon MC agreement exercises the simulation independently of
    # characteristic inversion, at fixed parameter/state and bounded path cap.
    horizons=[]
    for horizon in [1,6,63,252]:
        inp=replace(unit,horizon_trading_days=horizon)
        mc=option_pricing_result_asdict(price_european_options_monte_carlo(run.physical,run.risk,h_next=h,inputs=inp,config=MonteCarloPricingConfig(path_counts=(20000,80000),seed=101)))
        deterministic=deterministic_price(run.physical,run.risk,h,inp,800)
        mc['deterministic_price']=deterministic
        mc['straddle_z_vs_deterministic']=(mc['final']['straddle']['value']-deterministic['straddle'])/mc['final']['straddle']['standard_error']
        horizons.append(mc)
        run.status('completed cross-horizon numerical calculation '+str(horizon))
    # Check affine recursion away from normalization points using independent
    # 2D Gaussian integration of a two-period transform at complex u.
    from numpy.polynomial.hermite import hermgauss
    complex_checks=[]
    g1=run.physical.gamma1+run.risk.lambda1+.5;g2=run.physical.gamma2+run.risk.lambda2
    for nodes in [20,40,80]:
        x,w=hermgauss(nodes);z=x[:,None]*math.sqrt(2);e=x[None,:]*math.sqrt(2);weights=w[:,None]*w[None,:]/math.pi
        nxt=run.physical.omega+run.physical.beta*h+run.physical.alpha*(z-g1*math.sqrt(h))**2+run.physical.rho*(e-g2*math.sqrt(h))**2
        for u in [2j,20j,1+20j]:
            computed=np.sum(weights*np.exp(u*(-h/2+math.sqrt(h)*z)+.5*(u*u-u)*nxt))
            direct=transform(u,2,h,run.physical,run.risk)
            complex_checks.append({'nodes':nodes,'u':[u.real,u.imag],'absolute_error':float(abs(computed-direct))})
    result={'anchor_identification':boundary,'local_shape_identification':ident,'short_horizon_truncation_followup':short,
      'cross_horizon_mc':horizons,'complex_transform_gaussian_integration':complex_checks,
      'elapsed_seconds':time.monotonic()-started,'calibrations_performed':0,
      'reason_for_additional_calculation':'First results showed short-horizon cutoff sensitivity and effective anchor-state boundary; narrow diagnostics resolve those concerns.'}
    save(out/'additional-diagnostics.json',result)
    for key in ['pooled_vix_anchor']:
        comparison['fits'][key]['effective_state_boundary_diagnostic']=boundary
    save(out/'chronological-comparison.json',comparison)
    validation=json.loads((out/'structural-validation.json').read_text())
    validation['comparison']=comparison;validation['additional_diagnostics']=result
    save(out/'structural-validation.json',validation)
    # Preserve the full batch provenance and add this narrowly scoped calculation.
    prov=json.loads((out/'provenance.json').read_text())
    prov['additional_command']='bash research/curve_structural/diagnose.sh'
    prov['additional_seconds']=result['elapsed_seconds']
    save(out/'provenance.json',prov)
    run.status('additional diagnostics complete; preparing report')


if __name__=='__main__':main()
