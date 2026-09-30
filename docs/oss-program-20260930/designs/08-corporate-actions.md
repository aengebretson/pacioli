# Roadmap item 8 — Corporate-action algebras and entitlement projections

Status: proposed future wave; no implementation worker is assigned by this document. Baseline: OSS snapshot `20e46a6`, 2026-09-30. Roadmap reference: [v0.3 asset servicing](https://github.com/aengebretson/pacioli/blob/main/docs/roadmap.md#v03--asset-servicing--corporate-actions).

## Outcome and baseline

Represent asset servicing as explicit immutable economic facts and deterministic financial algebras. Reporting is a projection of those facts: entitlement, position, cash, settlement, and journal views share evidence and evaluation context. Reports never become a second authoritative ledger.

The baseline event variant contains cash movements and equity trades. Lifecycle resolution, lifecycle-aware portfolio projection, canonical serialization, and checkpoint application already exist. Corporate-action event types, entitlement rules, elections, and corporate-action accounting are absent. The fixture accounting policy deliberately rejects these events; extending it accidentally is not a delivery strategy.

## Phased increments

1. **Cash dividend entitlement.** Introduce a narrowly scoped declaration/evidence model and a typed entitlement calculation using explicitly supplied eligible holdings, record date, payment date, rate, currency, and policy version. Emit an entitlement projection and payment obligation; connect cash only through the agreed payment-recognition policy. Do not infer actual receipt from a scheduled payment date.
2. **Splits and reverse splits.** Add an ordered quantity transformation with an exact rational ratio, affected instrument identity, effective boundary, fractional entitlement, and rounding policy. Preserve pre-action and post-action lineage. Initially reject ambiguous same-time trade/action ordering.
3. **Distributions and reorganizations.** Model spin-offs and mergers as typed multi-instrument transformations. Supply successor identities, ratios, elections, cash components, and allocation evidence explicitly. Add cash-in-lieu and interest only after their distinct accrual and eligibility policies are specified.
4. **Corrections and accounting integration.** Resolve corrected declarations through immutable lifecycle semantics, invalidate dependent entitlement/state checkpoints, and regenerate projections and journals under the same context.

## Algebra and policy semantics

Entitlement maps operate on typed eligible quantity and rate; monetary and quantity reductions retain complete account, instrument, action, currency, and entitlement-kind keys. Exact addition claims laws only within its checked representable domain. A split followed by a sale is an ordered fold; it is not commutative. A merger spans instruments and cannot be partitioned into independent instrument folds without an explicit join/dependency contract.

Record-date eligibility, economic effect, knowledge cutoff, and payment/settlement date remain distinct. Rules for unsettled trades, short positions, withholding, election defaults, fractional shares, and rounding are named policies or unsupported cases, never implicit conventions. Derived entitlements retain contributing event and source identities plus action/policy versions.

## Dependencies and parallel boundaries

Depend on O2 lifecycle, O3 schema/checkpoint extension, O4 accounting boundaries, and O5 typed composition. Entitlement fixtures and policy design can proceed independently. Event-variant changes, serialization, and portfolio integration require one coordinated owner; accounting can follow the reviewed event contract. Lots need item 9 before basis allocations are supported.

## Independent acceptance criteria

Hand-calculated fixtures prove a dividend, a 2:1 split, a reverse split with fractional residual, and a late correction. Old knowledge-cutoff results remain reproducible. Full replay equals supported resumed replay; invalid resumes explicitly require rebuild. Tests expose unsupported ordering and missing election/rate inputs. Position/cash/journal outputs reconcile to separate observations without editing evidence. Every report row drills down to source records.

## Deferred decisions

No production tax treatment, market-specific entitlement convention, automated elections, legal interpretation, vendor feed, or complete corporate-action taxonomy is selected. Review those policies before expanding the first narrow event family.
