#!/usr/bin/env python3
"""Render the audit conclusions and explicit missing-data contract from local artifacts."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from audit import save, checkpoint

out=Path(sys.argv[1]).resolve()
f=json.loads((out/'feasibility.json').read_text())
i=json.loads((out/'evidence-inventory.json').read_text())
run=json.loads((out/'audit-run.json').read_text())
SOURCES={
 'iv_api':'https://raw.githubusercontent.com/IVolatility-com/API-docs/main/rest-api-ivlive-dev_formatted.json',
 'iv_intraday':'https://www.ivolatility.com/doc/Intraday%20data%20guide.pdf',
 'iv_trades':'https://www.ivolatility.com/doc/Intraday_options_trades_data_guide.pdf',
 'spx_specs':'https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications',
 'spx_fact':'https://cdn.cboe.com/resources/spx/spx-fact-sheet.pdf',
 'occ_rules':'https://www.theocc.com/getcontentasset/9d3854cd-b782-450f-bcf7-33169b0576ce/dfc3d011-8f63-43f6-9ed8-4b444333a1d0/occ_rules.pdf',
 'occ_calendar':'https://infomemo.theocc.com/infomemos?number=57897',
 'nyfed':'https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates'
}
pricing={
 'schema_version':1,'source_acceptance':'unaccepted','replay_ready':False,
 'numeric_discount':None,'numeric_october_forward':None,'numeric_option_fair_value':None,
 'vendor_curve':{'evidence':'evidence-inventory.json:rates','observation_dates':i['rates']['dates'],'rows':i['rates']['rows'],
 'available_at_decision':False,'original_publication_timestamp':None,'publication_evidence':'API equities/interest-rates: post-2021 ISDA Fallback, one-day delayed; later export creation is not original publication.',
 'tenor_unit':'unresolved: intraday guide p13 trading days versus trades guide p10 calendar days','rate_unit':'percent','day_count':None,'compounding':None,'interpolation':'nonstandard periods interpolated; algorithm unspecified','discount_curve_equivalence':'unqualified; fallback benchmark is not automatically a zero-coupon discount curve','prior_date_rows':i['rates']['prior_date_vendor_rows'], 'sources':[SOURCES[k] for k in ['iv_api','iv_intraday','iv_trades']]},
 'public_prior_date_evidence':{'inventory':i['staged_public_rates'],'eligible_maturity_curve':False,'documentation_only':'NY Fed SOFR/averages publication approximately 08:00 ET; possible 14:30 ET same-day revision. Actual/360 compounding for retrospective averages does not establish a future October discount curve. No September 24/25 vintage supplied.','source':SOURCES['nyfed']},
 'settlement':{'fixing_date':'2026-10-23','fixing_basis':'SPX component primary-market closing sales prices','scheduled_regular_close_utc':'2026-10-23T20:00:00Z','fixing_publication_timestamp':None,
 'normal_payment_date':'2026-10-26','payment_date_basis':'Next business day under ordinary exercise/acceptance and published 2026 calendar; future exceptional postponement remains possible.',
 'clearing_member_to_occ_deadline_utc':'2026-10-26T13:00:00Z','occ_to_clearing_member_deadline_utc':'2026-10-26T18:00:00Z','deadline_qualification':'OCC Chapter I Settlement Time and Rules 1805/1806. Directional at-or-before deadlines, conditional obligations; not exact transfers or broker-client timestamps.',
 'actual_payment_timestamp':None,'broker_customer_credit_timestamp':None,'pricing_payment_timestamp_adopted':None,'status':'scheduled fixing and normal payment date/deadlines documented; exact cash-flow normalization unresolved','sources':[SOURCES[k] for k in ['spx_specs','spx_fact','occ_rules','occ_calendar']]},
 'parity':{'one_strike':'Identifies one spread only; cannot independently identify discount and forward.','fixing_payment_separation':'For present values at t: C-P = D(t,Tpay)*(F_pay_measure(t,Tfix)-K). Tfix is the October close; Tpay is the later cash flow. Under stochastic rates this is a payment-numeraire expectation, not automatically an ordinary fixing-date forward.',
 'quoted_premium_normalization':'If premium quotes are paid at Tpremium, D(t,Tpremium)*(Cquote-Pquote) = D(t,Tpay)*(F_pay_measure-K), under common deterministic cash dates. Multi-strike slope then identifies D(t,Tpay)/D(t,Tpremium), not automatically D(t,Tpay).',
 'bounds_given_qualified_effective_discount':'K + [min Cbid - max Pask, max Cask - min Pbid]/D_effective. Only conditional observed-state outer bounds.','multi_strike_evidence':'No target-date quotes in supplied daily extract; only one strike in frozen intraday pair. No numerical parity regression performed.','multi_strike_minimum':'One additional distinct strike, both call and put, same fixing/payment/premium conventions and synchronized valid quotes; two strikes algebraically suffice, extra strikes needed for overidentification/robustness.',
 'multi_strike_interval_method':'For each strike require lower_i <= A-D_effective*K_i <= upper_i and D_effective>0; intersect feasible strips, do not regress arbitrarily selected midpoints.','december_es':'ESZ6 remains a December hedge; no October forward or basis model inferred.'},
 'decision':'Descriptive uncertainty audit feasible now; causal discount, forward and dollar fair-value comparison remain unavailable.',
 'current_documentation_limit':'Sources inspected now. No general claim of exact historical webpage vintage or future realized settlement. Original source qualification is not upgraded.'}
save(out/'pricing-input-status.json',pricing)

def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def spans(seconds):
    seconds=sorted(set(seconds));result=[]
    for t in seconds:
        if result and t==result[-1][1]:result[-1][1]=t+1
        else:result.append([t,t+1])
    return [[iso(a),iso(b)] for a,b in result]
decisions=[json.loads(x) for x in (out/'decisions.jsonl').open()]
reasons=sorted({r for d in decisions for r in d['reasons']})
gaps={r:spans([d['decision_epoch'] for d in decisions if r in d['reasons']]) for r in reasons}
save(out/'exclusion-intervals.json',{'interval_semantics':'Half-open UTC decision intervals, not assertions of missing exchange events. Exact selected source seconds are in decisions.jsonl.','by_reason':gaps})
requirements={'schema_version':1,'acquisition_authorized':False,'minimal_next_action':'Coordinator reviews descriptive-envelope semantics and requests an evidence-only check for an already-held pre-decision maturity curve with conventions. If none exists, separately authorize a narrowly scoped source request; this handoff makes no request.',
 'requirements':[
 {'id':'R1','enables':'Exact point observation ordering','instruments':['SPXW 261023 C7725 conId 919907940','SPXW 261023 P7725 conId 919909487','ESZ6 conId 515416632'],
 'source':'Existing broker historical response cannot supply missing sequence; require archived exchange/consolidated ordered quotes or a contemporaneously recorded stream with documented ordering and coverage.',
 'interval':'2026-09-25 [13:55,14:35) UTC frozen context. Minimal selected source-second intervals per instrument are in selected_source_intervals; these support ambiguity inspection only, not tape or receipt certification.',
 'selected_source_intervals':{n:[iso(min(d['inputs'][n]['source_second'] for d in decisions)),iso(max(d['inputs'][n]['source_second'] for d in decisions)+1)] for n in ['spxw_20261023_7725_call_bid_ask','spxw_20261023_7725_put_bid_ask','esz6_bid_ask']},
 'fields':['instrument/security master identity','event_timestamp with documented resolution and UTC mapping','source sequence and sequence scope','bid/ask prices and sizes','quote flags/venue or NBBO scope','cancel/correction/status linkage','gap/completeness evidence'],
 'not_solved_by':['deduplication','last row in file','a 5/30/60-second grid','a delay without measured latency bounds']},
 {'id':'R2','enables':'Causal as-of information set','source':'Archived contemporaneous receiver/dissemination record for options, ES, SPX and each chosen VIX index.',
 'interval':'2026-09-25 [13:55,14:35) UTC; causal cutoffs at each decision in [14:00,14:30).',
 'fields':['contemporaneous receipt timestamp','original publication timestamp for derived index','clock/timezone/synchronization error bound','event-to-receipt mapping','revision lineage','feed status and gap markers'],
 'smallest_alternative':'A documented conservative delivery upper bound plus proven complete ordered records can support a declared delay. No such bound is present.'},
 {'id':'R3','enables':'Five-index model input coverage under existing 60-second policy','source':'Existing contemporaneous Cboe index dissemination/receipt archive if held.','interval':'Exact decision gaps for VIX1Y and VIX3M in exclusion-intervals.json; predecessor input lookback at most 60 seconds.',
 'fields':['unrevised index value','original publication and receipt time','index identity/methodology','status flags'],
 'limitation':'Missing broker observations are not proven provider outages. Do not synthesize observations or widen the age cap to conceal gaps.'},
 {'id':'R4','enables':'Conditional single-strike October forward bounds and discounting','source':'Already-held USD maturity discount curve/zero-coupon price with original publication evidence; rate administrator/provider methodology.',
 'interval':'Latest demonstrably available vintage before 2026-09-25T14:00:00Z, plus any updates before 14:30; tenor to normal 2026-10-26 payment and separately chosen premium settlement date.',
 'fields':['original published_at and observed_at','observation date versus publication date','currency and collateral/funding basis','maturity/value dates','rate kind or discount factor','day count','compounding','business-day rule','interpolation method or exact maturity node','revision/as-of vintage','approved maximum age'],
 'minimum':'One qualified exact-horizon effective discount factor per applicable vintage is enough for interval parity with the existing strike; a whole curve or new strike is not inherently necessary.',
 'limitation':'A prior-day label or overnight SOFR alone does not establish term pricing; a flat carry scenario would be an explicit assumption, not an observed input.'},
 {'id':'R5','enables':'Alternative joint parity identification','source':'Same synchronized options source as R1/R2.','interval':'Same September 25 evaluation/context, October 23 PM expiry.',
 'fields':['one additional distinct strike with both call and put sides','all R1/R2 timing/validity fields','identical exercise, fixing, payment and premium conventions'],
 'limitation':'Use bid/ask feasible regions. A second strike is an alternative to independently qualified discounting, not a substitute for timing; real prices may only bound the solution.'},
 {'id':'R6','enables':'Correct fix/pay/premium horizon','source':'Cboe/OCC dated product rules and calendar; documented model cash-flow convention and applicable clearing/broker schedule, without account access.',
 'interval':'October 23 fixing and October 26 normal exercise payment; premium cash date for September 25 quote.',
 'fields':['fixing close timestamp','settlement-value publication/correction timestamp when realized','exercise acceptance convention','payment date and chosen pricing cash-flow time','premium cash date','deadline versus actual transfer distinction','timezone/DST','exception/postponement handling'],
 'resolved_now':['ordinary PM closing-price basis','normal following-business-day payment date','directional OCC clearing deadlines'],
 'unresolved':['actual realized payment','customer credit timing','pricing normalization of quoted premium to valuation time']}
 ],
 'defensible_now':['Exact reconciliation of preserved source-time strict exclusions','Duplicate/state diversity, observation-age and skew diagnostics','Conditional observed-state quote/parity intervals and declared sensitivity','Documentation and evidence-gap audit','Existing historical model/forecast work remains exploratory and requires its own scope'],
 'not_defensible_now':['Certified causal point replay','Exact standalone fills from complex prints','Every-print completeness','Causal October discount/forward or exact fair prices','Strategy P&L or profitable edge','Untouched out-of-sample claims on already inspected data']}
save(out/'data-requirements.json',requirements)

lines=['# Q2-T17 SPXW replay feasibility', '',
'**Decision: ready for coordinator review of the feasibility audit; replay remains unqualified and source acceptance remains unaccepted.** Original Q2-T16 strict results are preserved. No fills, strategy P&L, exact fair value or untouched evaluation are claimed.', '',
'Frozen evaluation: September 25, 2026 [14:00,14:30) UTC; context [13:55,14:35). October 23 PM SPXW 7725 call 919907940 / put 919909487; ESZ6 515416632 is a separate December hedge. Base `9e37f09030037b6618afdc4dccd9c8a6638843a7` is Q2-T14 review source, not accepted integration.', '',
'## Reconciliation and observation semantics', '',
'All 1,800 prior decision epochs, eligibility values and exclusion lists reconcile, as do component totals, trade classification totals, context row counts and the normalized-file SHA-256 in Q2-T16’s manifest. Acquisition completion means its 11-feed broker-history traversal; this worker did not repeat raw-page acquisition/pacing validation or certify exchange completeness. Inputs were read only.', '',
'`predeclaration.json` was hashed and timestamped before new scoring. Prior strict counts were already known. Strict selection takes the greatest source second strictly below the decision, admits ages <=5 seconds for options/SPX/ES and <=60 for VIX inputs, requires <=1-second core skew, valid prices/sizes/flags and one price pair per quote second. Size variation remains separately visible and cannot establish fills. No older clean quote is selected in place of an ambiguous latest quote.', '',
'Envelopes change only quote-price uniqueness. They retain every valid observed state at the selected second, strict freshness and synchronization, and unique index values. Combining side extrema forms a Cartesian outer bound; the endpoints need not have existed together. This is conditional on the supplied observations, not a bound on missing updates, actual transaction prices or receipt latency.', '',
'## Duplicates versus different states', '',
'Counts below use the full 40-minute context. An identical repeated state is informational redundancy, not proof of a duplicate exchange event. Price/size/flag identity and full-tick identity agree for these quote rows.', '',
'| Feed | Rows | Identical-state excess rows | Distinct states | Observed seconds | Seconds with different prices | Size/flag-only variation seconds |',
'|---|---:|---:|---:|---:|---:|---:|']
for n in ['spxw_20261023_7725_call_bid_ask','spxw_20261023_7725_put_bid_ask','esz6_bid_ask']:
 s=f['state_statistics'][n]['context'];lines.append(f"| {n} | {s['rows']} | {s['duplicate_identical_state_rows']} | {s['unique_states']} | {s['seconds']} | {s['seconds_multiple_price_pairs']} | {s['seconds_size_or_flag_only_variation']} |")
lines += ['', 'No multirow quote second becomes a single full state merely by collapsing identical rows. The original implementation already used distinct-state sets, so deduplication does not create point eligibility. Source-second counts differ from decision counts because each decision uses a prior second and can reuse it within the age limit. Context and evaluation populations are separately recorded in `feasibility.json`; no excluded row is silently erased.', '',
'## Synchronization and exclusions', '',
'| Criterion | Decisions / 1800 |','|---|---:|',
'| Strict option pair point | 0 |',f"| Strict ES point | {f['strict']['component_eligibility_counts']['hedge_point_seconds']} |",f"| All index inputs | {f['strict']['component_eligibility_counts']['all_index_inputs_seconds']} |",'| Strict synchronized point | 0 |',
f"| Option-pair envelopes | {f['envelopes']['option_pair']} |",f"| Option + SPX + ES envelopes | {f['envelopes']['core']} |",f"| Envelopes with all five VIX inputs | {f['envelopes']['all_inputs']} |",'| Certified contemporaneously available decisions | 0 |','',
'Exclusions overlap: ' + '; '.join(f'{k} = {v}' for k,v in f['strict']['decision_exclusion_counts'].items()) + '. Exact age distributions are in feasibility.json. No invalid quote flags/prices/sizes were found at selected seconds. See exclusion-intervals.json for decision gaps and decisions.jsonl for predecessor seconds and every envelope.', '',
'Evaluation-window trade classifications reconcile: ' + json.dumps(f['reconciliation']['trade_classifications']['recomputed']) + '. CBOE condition f remains a complex print exclusion. Empty conditions on the remaining put do not repair its ambiguous predecessor quote. No standalone execution or fill was promoted.', '',
'## Predeclared sensitivity and pessimistic bounds', '',
f"All {len(f['sensitivity'])} freshness/skew combinations retain zero point decisions. All-input envelope counts range from {min(x['envelopes'] for x in f['sensitivity'])} to {max(x['envelopes'] for x in f['sensitivity'])}; each fixed combination is in feasibility.json. No threshold was enlarged to obtain a target count.", '',
'| Grid seconds | Extra cutoff lag | Envelope coverage across every grid phase | Point decisions |','|---|---:|---|---:|']
for g in f['grid_sensitivity']:
 lines.append(f"| {g['grid_seconds']} | {g['lag_seconds']} seconds | {100*g['min_envelope_fraction']:.2f}%–{100*g['max_envelope_fraction']:.2f}% | 0 |")
lines += ['', 'The two-second-lag candidate uses source seconds strictly before t−2, with age measured from t and unchanged 5/60 caps. It is not adopted as causal replay: neither this delay nor a coarse grid supplies order, receipt time or a latency bound. Every phase is reported; no favorable phase is selected. These grids are not independent samples or new evaluation data.', '',
'For the option pair, the observed-state spread interval is [min Cbid - max Pask, max Cask - min Pbid]. Its width in index points is ' + json.dumps(f['bounds_distributions_points']['parity_width']) + '. The same width equals pessimistic displayed ask-sum minus bid-sum; this is neither a realizable round trip nor estimated transaction cost. Ask-sum uncertainty width is ' + json.dumps(f['bounds_distributions_points']['straddle_ask_uncertainty_width']) + '. Extremes were retained, not trimmed. Decimal arithmetic is used for bounds; quantiles are nearest-rank.', '',
'The unconditional lower bound on certified causal opportunities is zero. Without completeness/receipt evidence, these finite observed-state intervals cannot guarantee bounds on the actual market or future executions. There is no numerical strategy-profit bound.', '',
'## Pricing evidence and cash-flow clocks', '',
f"The {i['rates']['rows']:,} vendor rate rows and gzip agree and their saved hashes reconcile. All are dated September 25; no prior-date curve is supplied. The [official API]({SOURCES['iv_api']}) describes delayed fallback-rate data. Same-day EOD records are inadmissible at 14:00 UTC. The [intraday guide, p13]({SOURCES['iv_intraday']}) calls the period trading days; the [trades guide, p10]({SOURCES['iv_trades']}) calls it calendar days. Neither reviewed description establishes the required day count, compounding or interpolation algorithm. Percent units alone cannot yield a qualified discount factor.", '',
f"The staged public data contains {i['staged_public_rates']['rows']} EFFR/SOFR overnight observations spanning {i['staged_public_rates']['date_range']}, no September 2026 values, no original publication timestamps and no discount factors. [NY Fed methodology]({SOURCES['nyfed']}) documents approximately 08:00 ET publication, possible 14:30 ET revisions, and Actual/360 compounded historical SOFR averages. This does not turn an overnight observation or backward-looking average into an October maturity curve. A verified September 24 vintage published before the decision could be assessed if already held; none is present here.", '',
f"[Cboe specifications]({SOURCES['spx_specs']}) and its [fact sheet, p2]({SOURCES['spx_fact']}) support October 23 PM closing-price fixing, scheduled 16:00 New York / 20:00 UTC, and next-business-day cash delivery. This is not the timestamp when the final settlement value becomes published. [OCC’s 2026 calendar]({SOURCES['occ_calendar']}) implies normal payment on Monday October 26, subject to exceptional changes.", '',
f"[OCC rules]({SOURCES['occ_rules']}) Chapter I (PDF p14) and Rules 1805–1806 (pp173–174) distinguish the payment directions: member-to-OCC by 09:00 ET and OCC-to-member by 14:00 ET, under the stated conditions. On October 26 these correspond to 13:00 and 18:00 UTC. These are deadlines, not exact transfers or customer credit times. No exact pricing-payment instant has been adopted. Live document inspection is not proof of every historical document vintage.", '',
'Keep **Tfix**, **Tpay** and **Tpremium** separate. For present values, parity is `C−P = D(t,Tpay) × (F_pay_measure(t,Tfix)−K)`. Under deterministic rates the fixing expectation and payment discount can be separated; stochastic rates require the appropriate payment numeraire. If premiums are paid later, quoted prices require premium-date normalization; two-strike slope identifies an effective discount ratio unless that normalization is already supplied. Do not add weekend payment days to the underlying stochastic fixing horizon.', '',
'One strike supplies one spread equation. It cannot jointly identify discount and forward. Given a qualified effective discount, the saved quote envelope yields conditional forward bounds. An alternative is one additional same-expiry call/put strike with synchronized valid quotes; intersect bid/ask parity strips rather than selecting midpoints. More strikes are needed for diagnostics, and noisy intervals need not identify a unique solution. ESZ6 remains a hedge with a different maturity and basis.', '',
f"The daily option extract has {i['quote_counts']['rows']:,} rows spanning {i['quote_date_range'][0]} through {i['quote_date_range'][1]}. All six-field contract records reconcile their OSI date/right/strike; quote rows join to contract IDs without shape/identity errors. The eleven-field quote layout has no intraday time, receipt time or size; its quality flags include unknown quote clock and unverified settlement/analytics. It contains zero September 25 observations. No daily multi-strike pair was used for intraday parity. Existing daily index/calendar evidence has unverified historical publication/listing vintages.", '',
'## What is defensible and what is missing', '',
'Descriptive source-time state diversity, freshness/skew diagnostics, observed quote bounds and sensitivity are defensible now. Certified causal replay, exact option pricing, fills, every-print scoring and strategy P&L remain blocked. Previously inspected historical model/forecast studies remain exploratory; this audit neither reruns their fits nor upgrades their acceptance.', '',
'`data-requirements.json` separates the smallest fields and intervals: ordered option/hedge states; contemporaneous receipt/index publication lineage; exact stale-index gaps; one pre-decision qualified effective maturity discount (or one additional synchronized strike pair); and explicit fixing/payment/premium conventions. New acquisitions, provider contact and collector changes require a separate assignment and were not performed.', '',
'## Reproduction and actual checks', '',
'```bash',
'bash research/curve_feasibility/run.sh /home/andrew/luca-development/state/maintenance/vol-curve-20260930/feasibility/output',
'```', '',
f"The numerical audit completed in {run['elapsed_seconds']:.2f} seconds with peak RSS {run['max_rss_kib']/1024:.1f} MiB, 300-second timeout and 1536 MiB address-space cap. It uses the specified read-only Python executable, standard-library Decimal and no RNG. The executable resolves to Python 3.12.3 despite a Python 3.11.2 venv configuration; NumPy import failed. No packages were installed or modified. No fitted-model calculation depends on that broken numerical environment.", '',
'Actual checks: prior artifact SHA-256 and per-decision reconciliation; streamed CSV/OSI/schema and rate JSON/gzip reconciliation; public primary-document review; Python AST and shell syntax checks recorded in verification.json. No automated software tests, CTest, pytest, browser tests or CI ran. The inventory initially treated CSV period strings lexically; that implementation error was corrected to integers and rerun, with initial outputs retained. No candidate or threshold changed.', '',
'Public documentation snapshots are local under `public-documents/`. Direct OCC PDF captures returned HTTP 403; the successful web-tool text evidence is saved separately and must not be mistaken for original PDF bytes. Two attempted pdftotext reads of those absent files failed; no extracted PDF was claimed. See provenance and command records for the complete handoff.', '']
(out/'feasibility-report.md').write_text('\n'.join(lines))
checkpoint(out,'Feasibility report, pricing status and exact data requirements rendered')
print('Rendered feasibility-report.md, pricing-input-status.json, data-requirements.json, exclusion-intervals.json')
