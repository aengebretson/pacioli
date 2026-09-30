# LUCA OSS parallel implementation contract

Batch: `oss-20260930` (UTC date; September 29 local Chicago). Source baseline: `20e46a6a0c0744f9591968709adb0eb66aa5a411` in `aengebretson/pacioli`.

## Authorization and purpose
The user requested: “can we create a set of tmux workers on stbridget to work on these oss features. how much can we parallelize and get work done. create design docs for each feature and then start a set of tmux works on the tasks”. The user further specified: “we are sticking with the 'algebra' concepts and projections for reporting correct? I like that language and framework style”. This is direct authorization to prepare these designs and launch the bounded implementation batch. It is not represented as a separate website approval of unseen documents.

Preserve financial algebras and reporting projections as the public conceptual framework. Immutable evidence → normalized economic events → ordered lifecycle resolution → typed financial algebras/projections → positions, cash, settlements, journals, report views → reconciliation with separate observations. A projection is a named versioned deterministic derivation. An algebra specifies its domain, operations and laws with explicit preconditions. Keep ordered folds distinct from unordered reductions; do not claim universal commutativity, inverses, or partition independence. With fixed-width exact arithmetic, stated algebraic laws must account for intermediate overflow and domain restrictions.

## First wave
Five additional isolated workers are authorized for this manual batch, overriding the historical three-lane limit only for these recorded assignments. This does not change persistent automatic-dispatch configuration. The inspected host has 32 CPUs and approximately 229 GiB available memory. Each new worker is limited to 4 CPUs, 8 GiB memory and four hours, with no infinite retry. Five implementation streams is a dependency/ownership limit, not a fivefold delivery-time promise.

| Task | Session | Deliverable |
|---|---|---|
| O1-T04 | luca-oss-package | LUCA CMake identity/options with legacy compatibility; package examples and compiler CI definitions |
| O3-T11 | luca-oss-replay | New state-plus-refreshed-manifest API for already-compatible ordinary suffixes |
| O4-T04 | luca-oss-accounting | Settlement-date journal projection implementing the existing narrow fixture policy |
| O5-T06 | luca-oss-algebra | Typed public financial algebra/projection contracts plus independent report example |
| F1-T01 | luca-oss-reconciliation | Exact trade comparison with separate evidence and a pure bounded CSV observation adapter |

O2 has existing immutable lifecycle and portfolio adapters. Its remaining work is documented; this wave reuses their semantics rather than assigning a competing lifecycle rewrite. O3 replay preserves the existing conservative rejection of late corrections and incompatible contexts; advanced incremental invalidation is a later increment. Accounting and trade comparison use existing concrete APIs and do not wait for new generic contracts.

## Ownership and integration rules
Every task has an exact path allowlist. Only the package worker edits root CMake/presets and public package-consumer projects. Other workers use direct new public headers and lane-specific standalone compile projects; they leave exact root-registration changes as integration notes, not competing root edits. New headers under existing installed roots are already exported by the existing directory installation rules; new adapter install/target setup remains an explicit integration item.

No worker may edit a sibling checkout or shared planning. Existing ledger, portfolio, lifecycle, journal, canonical format and comparison APIs remain compatible. No worker may change existing canonical schemas/hashes to make a new interface easier. Use separate result types or additive overloads. Names suggested by feature designs are the first-wave public names; if an unavoidable conflict is discovered, write `INTERFACE_REQUEST.md` and proceed with independent work. Cross-lane shared abstractions are adapted by the coordinator after reviewing all results.

Financial outputs use exact values and explicit currency/rounding/context, deterministic ordering, version identifiers and complete available lineage. Authoritative functions have no hidden file/database/network access. A declared version is not proof of correctness or compliance; do not characterize fixture-only accounting as production GAAP/IFRS/tax/NAV. No runtime plugin loader or expression language is included.

## Preserved operating boundaries
The user's standing pause on automated software tests, automatic reviews/repair loops, staging and deployment remains in force. Workers may author tests/fixtures, inspect code, and run necessary configure/compile/type-check/package commands. They must not run CTest, unit/integration/conformance scripts, test executables, CI, software benchmark suites, browser tests or deployment. Do not conceal test execution inside build commands; inspect custom build targets before use. A compiled executable is not an accepted result. Later verification plans must be specific and marked pending.

Workers do not commit, push, merge, tag, publish releases, access production data, place orders, access live providers or secrets, launch further agents, or modify the Docker engine. The established isolated runner mounts each checkout writable and common Git metadata read-only. Necessary model authentication follows the configured worker mechanism and is never placed in prompts, reports or source. Existing stbridget sessions and production services are preserved.

## Handoff
Read the runtime `INBOX.md` before major edits and at final handoff; update `STATUS.md` at least every five minutes. Initial acknowledgement must name task, source/design revision, scope, dependencies and preserved pause. Produce `HANDOFF.md`, `CHANGED_FILES.txt`, `INTEGRATION.md` and `handoff.json` in the assigned output directory. JSON has exactly `status` (`review` or `blocked`), `summary`, `tests` (actual compilation evidence and pending checks), and `limitations`. Retain actionable gaps, interface decisions, new target registration requirements and exact commands for later verification. Process exit is not completion; `review` means a reviewable diff, not integrated/released.

## Following waves
After reviewing these first-wave interfaces, prepare the portable accounting/replay/report CLI and Python hosts plus a platform adapter pinned to the reviewed OSS revision. Converge on contribution → purchase → settlement → correction/reversal → positions/cash/settlement + balanced journals → deliberate reconciliation breaks. Standalone and hosted canonical results must agree before claiming the milestone accepted. Corporate actions, expanded accounting, securities finance and scale/adapters follow their feature designs and explicit readiness decisions. They are not silently launched by this batch.

## Source of truth
Designs are copied identically into the dedicated OSS design branch and canonical platform planning under `planning/designs/oss-20260930/`. Task specs reference design digests and seed commit. The manual registry records current launch/run evidence separately from historical scheduler assignment state. New task specs remain `backlog` to avoid accidental automated duplicate dispatch; this batch's manual status is explicit. No automatic monitoring/relaunch is installed.
