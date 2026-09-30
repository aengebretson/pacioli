"""Offline numerical diagnostics for the k=1 saved HN-GARCSH research model.

No I/O, data acquisition, fitting policy, or production integration lives here.
The affine transform below is derived by integrating the two Gaussian shocks
in the implemented Q recursion; it is not a copied/unavailable paper formula.
"""
from __future__ import annotations

import cmath
import math
import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar


def expected_average(h, persistence, intercept, periods):
    """Closed affine expectation; fractional periods are analytic sensitivity only."""
    t = np.asarray(periods, dtype=float)
    if not 0 < persistence < 1 or np.any(t <= 0):
        raise ValueError('require 0 < persistence < 1 and positive periods')
    a = -np.expm1(t * math.log(persistence)) / (t * (1 - persistence))
    return a * np.asarray(h)[..., None] + (1 - a) * intercept / (1 - persistence)


def curve(h, persistence, intercept, periods):
    if np.any(np.asarray(h) <= 0):
        raise ValueError('nonpositive state')
    return 100 * np.sqrt(252 * expected_average(h, persistence, intercept, periods))


def anchor_state(vix, persistence, intercept, periods=21):
    a = -math.expm1(periods * math.log(persistence)) / (periods * (1-persistence))
    return (np.square(np.asarray(vix)/100)/252 - (1-a)*intercept/(1-persistence))/a


def bounded_scan(objective, lower, upper, *, points=10001, checkpoint=None):
    """One fixed grid and one local refinement, including boundary objectives."""
    grid = np.linspace(lower, upper, points)
    values = np.empty(points)
    for i, p in enumerate(grid):
        values[i] = objective(float(p))
        if checkpoint is not None and i % 1000 == 0:
            checkpoint(i, float(p), float(values[i]))
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError('no feasible training point; no calibration performed')
    best = int(np.argmin(values))
    lo, hi = grid[max(0, best-1)], grid[min(points-1, best+1)]
    result = minimize_scalar(objective, bounds=(lo, hi), method='bounded',
                             options={'xatol':1e-12, 'maxiter':150})
    candidates = [(float(grid[best]), float(values[best])),
                  (float(result.x), float(result.fun))]
    p, loss = min(candidates, key=lambda x:x[1])
    # Descriptive objective support, NOT a likelihood confidence interval.
    support = grid[finite & (values <= loss + 0.25)]
    eps=1e-5
    curvature=None
    if lower < p-eps and p+eps < upper:
        f0,f1=objective(p-eps),objective(p+eps)
        if math.isfinite(f0) and math.isfinite(f1):
            curvature=(f0-2*loss+f1)/eps**2
    return {'pQ':p,'mse_vix_points':loss,'rmse_vix_points':math.sqrt(loss),
            'grid_points':points,'finite_grid_points':int(finite.sum()),
            'refinement_evaluations':int(result.nfev),'refinement_success':bool(result.success),
            'bounds':[lower,upper],'grid_optimum':float(grid[best]),
            'near_boundary':bool(min(p-lower,upper-p)<1e-5),
            'objective_curvature_per_pQ_squared':curvature,
            'descriptive_grid_support_mse_within_0_25':[float(support.min()),float(support.max())] if support.size else [],
            'support_is_confidence_interval':False}


def transform(u, horizon, h, physical, risk):
    """E[(S_T/F)^u] using Gaussian integration of the k=1 Q process.

    If remaining payoff transform is exp(A+B*h'), integrate z and epsilon:
    denominators d_z=1-2*alpha*B and d_e=1-2*rho*B. Complete squares.
    This checks the simulated transition independently of Monte Carlo noise.
    """
    if physical.k != 1:
        raise ValueError('derived recursion restricted to k=1')
    g1=physical.gamma1+risk.lambda1+0.5
    g2=physical.gamma2+risk.lambda2
    a=b=0j
    for _ in range(horizon):
        dz=1-2*physical.alpha*b
        de=1-2*physical.rho*b
        an=a+b*physical.omega-0.5*cmath.log(dz)-0.5*cmath.log(de)
        bn=(-0.5*u+b*(physical.beta+physical.alpha*g1*g1+physical.rho*g2*g2)
            +(u-2*b*physical.alpha*g1)**2/(2*dz)
            +(-2*b*physical.rho*g2)**2/(2*de))
        a,b=an,bn
    return cmath.exp(a+b*h)


def deterministic_price(physical,risk,h,inputs,cutoff=400.0,tolerance=1e-8):
    """Finite-cutoff Fourier inversion, quadrature error and truncation separated.

    P1/P2 inversion of the independently derived transform. Put uses analytical
    parity and is therefore not independent evidence of put-call parity.
    """
    log_m=math.log(inputs.strike/inputs.forward)
    def integrand(x,shift):
        u=shift+1j*x
        return (cmath.exp(-1j*x*log_m)*transform(u,inputs.horizon_trading_days,h,physical,risk)/(1j*x)).real
    integrals=[]; errors=[]
    for shift in (1,0):
        value,error=quad(integrand,0,cutoff,args=(shift,),epsabs=tolerance,
                         epsrel=tolerance,limit=300)
        integrals.append(0.5+value/math.pi);errors.append(error/math.pi)
    d,f,k,m=inputs.discount_factor,inputs.forward,inputs.strike,inputs.contract_multiplier
    call=d*(f*integrals[0]-k*integrals[1])*m
    put=call-d*(f-k)*m
    return {'call':call,'put':put,'straddle':call+put,'cutoff':cutoff,
            'quadrature_tolerance':tolerance,
            'call_quadrature_error_estimate':d*(f*errors[0]+k*errors[1])*m,
            'probabilities':integrals,'parity_residual_by_construction':call-put-d*(f-k)*m,
            'put_derived_from_parity':True,'truncation_error_not_in_quadrature_estimate':True}


def gaussian_transition_diagnostic(physical,risk,h):
    """Tensor Gauss-Hermite integration of one Q step and a future exponential."""
    from numpy.polynomial.hermite import hermgauss
    g1=physical.gamma1+risk.lambda1+0.5;g2=physical.gamma2+risk.lambda2
    result=[]
    for order in (20,40,80):
        x,w=hermgauss(order);z=x[:,None]*math.sqrt(2);e=x[None,:]*math.sqrt(2)
        weights=w[:,None]*w[None,:]/math.pi
        nxt=physical.omega+physical.beta*h+physical.alpha*(z-g1*math.sqrt(h))**2+physical.rho*(e-g2*math.sqrt(h))**2
        result.append({'order':order,'normalization_error':float(weights.sum()-1),
          'forward_ratio_error':float(np.sum(weights*np.exp(-h/2+math.sqrt(h)*z))-1),
          'variance_expectation_error':float(np.sum(weights*nxt)-(physical.innovation_intercept+(physical.beta+physical.alpha*g1*g1+physical.rho*g2*g2)*h))})
    return result
