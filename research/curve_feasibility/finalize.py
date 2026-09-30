#!/usr/bin/env python3
"""Package a manual research handoff; syntax and artifact reconciliation only."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo
from audit import digest, save, utc

out=Path(sys.argv[1]).resolve()
source=Path(__file__).resolve().parent
root=source.parents[1]
readiness=Path('/home/andrew/vol-term-structure/data/replay-workers-20260929/qualify-session')
reference=Path('/home/andrew/luca-development/state/maintenance/vol-curve-20260930/reference')
control=Path('/home/andrew/luca-development/control/planning')
print('Final INBOX:',(out/'INBOX.md').read_text().strip())
f=json.loads((out/'feasibility.json').read_text())
i=json.loads((out/'evidence-inventory.json').read_text())
a=json.loads((out/'audit-run.json').read_text())
checks=[]
for p in sorted(source.glob('*.py')):
    ast.parse(p.read_text(),filename=str(p))
    checks.append('AST syntax parsed '+str(p.relative_to(root)))
shell=subprocess.run(['bash','-n',str(source/'run.sh')],capture_output=True,text=True,timeout=10)
if shell.returncode:raise ValueError(shell.stderr)
checks.append('bash -n research/curve_feasibility/run.sh: exit 0')
for name in ['feasibility.json','pricing-input-status.json','data-requirements.json','predeclaration.json','evidence-inventory.json','exclusion-intervals.json']:
    json.loads((out/name).read_text())
checks.append('Six required analytical JSON documents parse')
if not all(v['matches'] for v in f['reconciliation'].values()):raise ValueError('Prior reconciliation mismatch')
checks.append('All prior aggregate and 1800 per-decision artifact reconciliations match')
if i['schema_errors'] or not i['rates']['json_csv_semantic_match'] or not i['rates']['periods_contiguous'] or not all(i['rates']['original_hash_checks'].values()):raise ValueError('Inventory mismatch')
checks.append('Local CSV shape/contract identity and rate JSON/gzip/hash/period reconciliation match')
prior_hashes={e['path']:e for e in a['input_hashes']+i['input_hashes']}
changed=[]
for name,entry in prior_hashes.items():
    if digest(Path(name))['sha256']!=entry['sha256']:changed.append(name)
if changed:raise ValueError('Used input changed: '+repr(changed))
checks.append(f'Final SHA-256 recheck: {len(prior_hashes)} audit/inventory inputs unchanged since calculations')
clock={'fix':datetime(2026,10,23,16,tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat(),
       'member_to_occ':datetime(2026,10,26,9,tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat(),
       'occ_to_member':datetime(2026,10,26,14,tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()}
checks.append('ZoneInfo arithmetic confirms October close and directional deadline UTC conversions; no actual transfer inferred')
base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
branch=subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()
status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)
if base!='9e37f09030037b6618afdc4dccd9c8a6638843a7':raise ValueError('Wrong base')
paths=[line[3:] for line in status.splitlines()]
if any(not p.startswith('research/curve_feasibility/') for p in paths):raise ValueError('Out-of-scope diff')
checks.append('git status --porcelain --untracked-files=all: source changes confined to research/curve_feasibility/')
(out/'CHANGED_FILES.txt').write_text('\n'.join(paths)+'\n')
(out/'git-status.txt').write_text(status)
# Save an unstaged reviewable patch without modifying the Git index.
with (out/'source-review.diff').open('w') as dest:
    for p in sorted(source.iterdir()):
        if p.is_file():
            diff=subprocess.run(['git','diff','--no-index','--','/dev/null',str(p.relative_to(root))],cwd=root,capture_output=True,text=True,timeout=10)
            if diff.returncode not in (0,1):raise ValueError(diff.stderr)
            dest.write(diff.stdout)
checks.append('Saved source-review.diff using read-only git diff --no-index; no staging or commits')
verification={'checked_at':utc(),'type':'syntax and artifact reconciliation, not automated software tests','checks':checks,'clock_arithmetic':clock,'automated_software_tests_run':False,'known_failed_checks':['Pinned Python import numpy/scipy preflight failed at numpy; environment left unchanged.','Direct OCC PDF byte captures returned HTTP 403; web-tool extracts used instead.','Two pdftotext reads failed because denied OCC PDFs were absent.','Initial inventory compared period strings lexically; corrected integer conversion and reran inventory, preserving initial evidence.']}
save(out/'verification.json',verification)
extra=[root/'AGENTS.md',root/'docs/DEVELOPMENT_WORKFLOW.md',reference/'WORKER_POLICY.md',reference/'DEVELOPMENT_WORKFLOW.md',reference/'pricing-validation.md',reference/'fixed-parameter-objective-check.json',out.parent/'assignment.json',control/'tasks/Q2-T17.md',control/'increments/Q2-I17.md',control/'tracks/VOL_CURVE_RESEARCH_20260930.md',control/'approvals/A-VOL-CURVE-20260930-Q2-I17.json',
       readiness/'REPORT.md',readiness/'pricing-input-status.json',readiness/'existing-rate-evidence-check.json',readiness/'review.py',Path('/home/andrew/luca-development/state/maintenance/spx-trading-next-20260928/reference/README.md'),Path('/home/andrew/luca-development/state/runs/Q2-T14-20260928171645-eee620/output/research-venv/pyvenv.cfg')]
inputs={p:entry for p,entry in prior_hashes.items()}
for p in extra:inputs[str(p.resolve())]=digest(p)
source_hashes=[digest(p) for p in sorted(source.iterdir()) if p.is_file()]
public_hashes=[digest(p) for p in sorted((out/'public-documents').iterdir()) if p.is_file()]
limitations=[
 'Review only; source remains unaccepted and Q2-T14 base is not accepted integration.',
 'Second-resolution history lacks proven contemporaneous receipt and same-second ordering; quote envelopes are conditional descriptive bounds.',
 'No pre-decision maturity discount, separately identified October forward, or adopted exact payment/premium normalization; no numerical fair price.',
 'No exact fills, complex-leg standalone scoring, exchange-tape completeness, P&L or profitable-edge claim.',
 'All previously inspected historical research remains exploratory; no untouched holdout claim.',
 'Pinned venv metadata/executable mismatch and unavailable NumPy remain unrepaired; standard-library audit completed.',
 'OCC source read through web text; original PDF byte capture denied. Current documentation is not a full historical-vintage certification.',
 'No automated software tests, model fit, new market data, collector/core/shared-interface changes, commits, pushes or deployment.'
]
summary=f"Q2-T17 feasibility audit complete: original {f['strict']['eligible_synchronized_point_decisions']}/{f['strict']['decision_count']} point decisions reconciled; {f['envelopes']['all_inputs']} all-input descriptive envelopes. Duplicates, real state ambiguity, sensitivity, pricing clocks and exact evidence gaps documented. Ready for coordinator review; causal replay remains unavailable."
tests=[
 'env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 30 '+a['executable']+' -B -c "import sys,numpy,scipy": failed numpy import; no environment changes.',
 'bash research/curve_feasibility/run.sh '+str(out)+' (initial audit-only launcher): exit 0; normalized stream, prior decisions and fixed sensitivity family reconciled. Runtime '+str(round(a['elapsed_seconds'],3))+' seconds.',
 'env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout --kill-after=10s 120 '+a['executable']+' -B research/curve_feasibility/inventory.py '+str(out)+': exit 0 after string-to-integer period correction; initial outputs retained.',
 'env PYTHONDONTWRITEBYTECODE=1 timeout 60 '+a['executable']+' -B research/curve_feasibility/report.py '+str(out)+': exit 0; report, pricing status, data requirements and exclusion intervals rendered.',
 'Public primary documentation inspected through web tool; env PYTHONDONTWRITEBYTECODE=1 timeout --kill-after=5s 180 '+a['executable']+' -B research/curve_feasibility/capture_docs.py '+str(out)+': five byte snapshots saved; two OCC downloads HTTP 403; saved web extract instead.',
 'env PYTHONDONTWRITEBYTECODE=1 timeout 60 '+a['executable']+' -B research/curve_feasibility/finalize.py '+str(out)+': syntax, JSON, input hashes, UTC arithmetic and scope reconciled; see verification.json.'
]
save(out/'handoff.json',{'status':'review','summary':summary,'tests':tests,'limitations':limitations})
(out/'INTERFACE_REQUEST.md').write_text('''# Proposed future interface clarification — no shared change made

No cross-scope change is necessary to review this feasibility audit.
For a separately assigned pricing/replay implementation, distinguish event time,
publication time, contemporaneous receipt time, retrieval time, sequence scope,
fixing time, settlement-value publication, payoff payment date/time convention,
and premium payment date. Carry quote-side uncertainty/quality and source status
explicitly. Do not silently overload one expiry timestamp for all cash-flow clocks.

Coordinator action: review the R1–R6 evidence requirements in data-requirements.json.
No source requests, new collector fields, production interface edits or planning
changes are performed or authorized by this proposal.
''')
(out/'HANDOFF.md').write_text(f'''# Q2-T17 coordinator handoff

Status: **review** — research deliverables ready for coordinator review; not accepted,
integrated or deployed. No dependency waits. Base `{base}`; branch `{branch}`.

{summary}

Completed criteria: all five assignment criteria addressed — preserved Q2-T16
reconciliation; duplicate/distinct-state audit; predeclared strict/envelope/delay
sensitivity; rate and fixing/payment documentation review; exact missing-data
requirements and reproducible offline source. Source edits are confined to
`research/curve_feasibility/`. No prior raw/input files were edited.

Missing empirical prerequisites: ordering/receipt and source qualification, a causal
maturity discount or synchronized extra strike pair, and an explicit pricing cash
convention. These are replay prerequisites, not unperformed feasibility work.
No automated software tests were run. Actual checks and failures are recorded in
`verification.json` and the exact four-key `handoff.json`.

Main artifacts (all under `{out}`):

- `feasibility-report.md`, `feasibility.json`
- `pricing-input-status.json`, `data-requirements.json`, `provenance.json`
- `predeclaration.json`, `predeclaration-receipt.json`
- `decisions.jsonl`, `source-second-audit.jsonl`, `exclusion-intervals.json`
- `evidence-inventory.json`, `audit-run.json`, `verification.json`
- `public-document-captures.json`, `public-documents/`, `commands.json`
- `CHANGED_FILES.txt`, `source-review.diff`, `INTERFACE_REQUEST.md`

Reproduce offline (all stages are bounded; does not redo public-document reads):

```bash
bash research/curve_feasibility/run.sh {out}
```

This command regenerates current audit/report files in the assigned output directory;
the original predeclaration receipt is preserved. To retain an earlier run, use a
fresh subdirectory of output and copy the manual documentation evidence as needed.
Final packaging is separate: `timeout 60 {a['executable']} -B research/curve_feasibility/finalize.py {out}`
with `PYTHONDONTWRITEBYTECODE=1`. It requires `INBOX.md` and the documented review evidence.
The complete final launcher was syntax checked; its three analysis stages were
executed separately, and the earlier audit-only launcher ran once. No repeated
numerical run was performed merely to re-label it a test.

Smallest next action: review adoption of the descriptive-envelope result, then check
for an **already-held**, pre-decision maturity discount with complete conventions.
If absent, separately assign the precise R4 evidence request or R5 parity alternative,
while retaining R1/R2 timing prerequisites. Do not restart acquisition automatically.

Limitations:

'''+ '\n'.join('- '+x for x in limitations)+'\n')
statusd=json.loads((out/'STATUS.json').read_text())
statusd.update(status='review',phase='Handoff complete; source unaccepted; causal replay remains blocked',updated_at=utc(),model_assignment={'model':'gpt-6-astra','reasoning_effort':'high','evidence':'assignment.json; runtime model selection not introspected'},completed_criteria=[1,2,3,4,5],summary=summary)
save(out/'STATUS.json',statusd)
with (out/'STATUS.md').open('a') as stream:stream.write('\n- '+utc()+' — **review**: '+summary+' Final INBOX read; no pending refinements.\n')
provenance={'schema_version':1,'task':'Q2-T17','base_commit':base,'branch':branch,'generated_at':utc(),'source_status':'unaccepted','integration_claimed':False,'original_inputs_preserved':True,'model_assignment':statusd['model_assignment'],'seed':None,'randomness':'none','commands':'commands.json','actual_checks':'verification.json','scope_status':status,'input_hashes':list(inputs.values()),'source_hashes':source_hashes,'public_evidence_hashes':public_hashes,'timing_assumptions':'predeclaration.json and pricing-input-status.json','exclusions':'feasibility.json / exclusion-intervals.json / decisions.jsonl','environment':{'python':a['python'],'executable':a['executable'],'thread_environment':{k:'1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS','BLIS_NUM_THREADS']},'numpy_usable':False,'modified':False},'limitations':limitations,'not_reinspected':['Q2-T16 raw response payloads and acquisition pacing (prior manifest evidence only)','Q2-T14 empirical model fit outputs','Q2-T15 36-origin results','VIX historical CSV values (not needed for this frozen intraday audit)']}
# No recursive self-hash; status/inbox/logs may receive later coordinator updates.
provenance['artifact_hashes']=[digest(p) for p in sorted(out.iterdir()) if p.is_file() and p.name not in ['provenance.json','STATUS.md','STATUS.json','INBOX.md','finalize.log'] and not p.name.endswith('.tmp')]
save(out/'provenance.json',provenance)
print(json.dumps({'status':'review','source_files':len(paths),'checks':len(checks),'provenance_inputs':len(inputs)}))
