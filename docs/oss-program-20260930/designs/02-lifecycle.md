# O2 — Immutable lifecycle algebra and reporting projections

Status: coordinator-authored implementation design, 2026-09-30. Baseline: OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. This records the user's requested direction and does not claim separate design approval or completed validation.

## Outcome and existing foundation

One immutable financial history must support reproducible historical reporting, late corrections, cancellations, and explicit reversals. Financial algebra is the framework language: lifecycle resolution is an ordered fold; positions, settled cash, settlement obligations, and journals are projections of the resolved economic evidence. Reporting is a derived view, never an alternative source of financial truth.

The baseline already implements `LifecycleRecordDraft::{originate,correct,cancel,reverse}`, transactional `LifecycleLedger::accept_batch`, and `resolve(recorded_through, economic_as_of)` in `luca/lifecycle.hpp`. It preserves immutable records and causal lineage. `luca/portfolio/lifecycle_projection.hpp` already implements `project_lifecycle`, passing one selected active set into the existing position, cash, and settlement engines. O2 is therefore a closure and usability increment, not a new event engine. The final paragraph of `docs/event-lifecycle.md` still defers journals even though the baseline now contains a trade-date journal projection; documentation needs reconciliation with implementation.

## Semantics and proposed boundary

Keep acceptance order ledger-local and deterministic. Knowledge selection is inclusive at `recorded_through`; economic selection is inclusive at `economic_as_of`; settlement eligibility uses an independently supplied date. Corrections replace the selected chain head, cancellations suppress it, and reversals create a separate explicitly linked economic event. None implies a universal inverse or permits arithmetic subtraction of arbitrary old projections.

The next bounded API increment should offer an owned evaluation envelope around the existing resolution and portfolio results, retaining the exact three cutoffs and ordered active-record, lifecycle-record, economic-event, and source-record identities. A proposed `LifecycleEvaluation` must own its evidence if it outlives the ledger. Current `LifecycleResolution` references can be invalidated when acceptance reallocates storage; an envelope must not imply otherwise. Select a name and exact fields in a focused implementation task before publishing the API.

Existing independent projection error results remain compatible. A report may describe a failed cash projection beside a successful position projection, but cannot present that aggregate as a wholly successful financial calculation. No existing API is silently changed to all-or-nothing behavior. The envelope cannot widen a resolution made at an earlier economic cutoff or claim to validate omitted knowledge without the original records.

## Delivery and dependencies

First wave: do not edit shared lifecycle headers while accounting, replay, and custom-report workers consume them. Those workers use the integrated resolver directly. A later O2 closure task owns the new envelope header, dedicated example, documentation update, and focused fixture additions; it depends on agreement about evidence fields with O3. It does not depend on an unimplemented generic algebra runtime.

Partial reversals, repeated independent reversals, corrections across financial keys, and actions targeting reversal records remain unsupported. Persistence, concurrency, transport, and global sequence allocation are outside this algebra.

## Acceptance and planned verification

Use a contribution, purchase, correction, settlement, and exact reversal. Earlier knowledge views must remain reproducible; later views select the corrected head without losing its predecessor evidence. Cash, positions, settlements, and journal consumers must identify the same selected records and cutoffs. Cancelled chains remain inspectable without contributing active payloads. Failure leaves accepted history unchanged.

Planned checks cover the existing lifecycle and lifecycle-projection cases plus owned-envelope lifetime, cutoff consistency, and rejected unsupported chains. Compilation may be performed. Software tests and deployments remain paused under the user's standing instruction; no tests were executed while authoring this design, and acceptance remains pending.
