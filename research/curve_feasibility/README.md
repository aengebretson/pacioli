# Q2-T17 offline feasibility audit

This isolated research module audits the frozen September 25 SPXW/ES evidence.
It does not alter LUCA core, accept a source, request market data, simulate fills
or calculate strategy P&L. All licensed observations and generated results belong
in the assigned external runtime `output/`, never this source directory.

Run from this worktree:

```bash
bash research/curve_feasibility/run.sh /home/andrew/luca-development/state/maintenance/vol-curve-20260930/feasibility/output
```

The launcher preserves an existing predeclaration receipt or writes one before
scoring in a fresh external output directory. The original receipt records that
Q2-T16 results were already known. It runs the offline audit (300-second limit,
1536 MiB address-space cap), local inventory (120 seconds) and report (60 seconds).
Library thread counts are one, bytecode writes are disabled, and all calculations
use the specified read-only Python executable and its standard library. No
third-party numerical package is needed. There is no random seed because there
is no RNG. No automated software tests are included or invoked.

`predeclare.json` freezes identity, timing, validity, envelope and sensitivity
rules. `audit.py` streams the normalized JSONL, counts repeated states separately
from genuinely different quotes, reconciles prior decisions, and writes exact
per-second details. It never treats callback/file order as event order.
`inventory.py` inspects the supplied rate, daily-option and calendar evidence.
`report.py` renders the result and identifies missing inputs. Aggregates are
conditional source-time descriptions, not contemporaneous availability evidence.

`capture_docs.py OUTPUT` is an **optional online public-document-only** command;
it is not called by the offline launcher. It uses a fixed public methodology URL
list, no authentication, a 20-second per-document timeout, 12 MiB cap and no retry.
Wrap it in `timeout 180`. Captured bytes can drift with current documentation.
The completed manual review also used the web tool for exact primary citations;
OCC original-PDF downloads were denied and its web text evidence is retained in
runtime output instead. Re-running the offline scripts does not repeat or upgrade
that human/model documentation review.

`finalize.py OUTPUT` records input/source/artifact hashes and the review handoff
once the documented checks and public evidence are present. This is a packaging
step, not a test runner. Read `output/INBOX.md` before handoff. Review status means
ready for the coordinator, never accepted, integrated or deployed.
