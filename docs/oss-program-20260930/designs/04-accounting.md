# O4 — Accounting algebras and journal projections

Status: coordinator-authored implementation design, 2026-09-30. Baseline: OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. The first implementation increment is settlement-date recognition under the existing fixture policy.

## Outcome and implemented baseline

Accounting should be expressed as a versioned financial algebra over lifecycle-resolved evidence. A journal mapping creates balanced entries; an exact reduction derives balances; reporting projections present journals and controls with explainable lineage. All use the same economic history as positions, cash, and settlement obligations.

The baseline already supplies immutable `JournalLine` and `JournalEntry` factories in `luca/accounting/journal.hpp`, plus `project_trade_date_journals` and its context/result types in `trade_date_projection.hpp`. Factories enforce positive fixed-point amounts, one currency, balanced debits and credits, stable identities, and matching lineage. The implemented projection consumes `LifecycleResolution`, validates explicit cutoffs, and retains selected evidence and policy/engine versions. `docs/accounting-foundations.md` and its portable fixture already specify both trade-date and settlement-date policies, but only the former has a public projection implementation.

## Bounded first-wave increment

Implement `luca/accounting/settlement_date_projection.hpp` with `SettlementDateProjectionContext`, `SettlementDateProjectionResult`, `SettlementDateProjectionError`, and `project_settlement_date_journals(const LifecycleResolution&, SettlementDateProjectionContext)`. Follow the ownership and result-envelope conventions of the existing trade-date projection without modifying its behavior or depending on new generic framework code.

Use the documented `fixture.settlement-date.v1` policy, version `1`. Positive USD contributions post debit cash and credit contributed capital on their effective date. An ordinary positive equity purchase produces no journal until its supplied settlement date; then debit equity securities and credit cash. An accepted exact-offset equity reversal posts debit cash and credit equity securities at its own settlement date. Before settlement, the economic position and open obligation can exist with no corresponding journal recognition; report this as the named policy difference.

Use existing exact valuation: absolute quantity multiplied by price, half-even once to scale-six money. Zero-valued postings, overflow, unsupported currency/event, invalid reversal treatment, inconsistent dates, cutoffs, ordering, and identities return typed errors. Validate the same resolved input evidence even if an event has not yet generated a journal. Preserve original, correction, and reversal provenance in every relevant entry and line. Date recognition never changes the original economic effective time.

Deterministic IDs must have their own settlement-date namespace, follow fixture expectations where specified, and reject alias collisions. Present entries by recognition date, acceptance sequence, phase ordinal, and identity. Return a complete owned result or error, never a partially accepted journal set.

## Boundaries and parallel execution

The accounting worker owns only the new header, a dedicated unit source and example, and a lane-specific documentation note. It does not refactor journal factories, trade-date code, lifecycle APIs, umbrella headers, or root build files. Integration of exports/build targets is reserved to the coordinator. The existing headers remain physically under `libs/ledger`; moving them into a new accounting package is a separately scheduled migration.

No policy ABI, runtime plugins, GAAP/IFRS claims, production chart, tax, NAV, cost basis, accruals, sells beyond exact reversals, fees, FX, or settlement calendars are introduced. Those need later financial policies and conformance evidence.

## Acceptance and planned verification

The existing contribution/purchase/correction/reversal walkthrough must yield documented settlement-date entries. Unsettled purchases leave accounting cash unchanged while portfolio obligations remain visible; settled accounting cash agrees with portfolio cash. Historical knowledge views and correction lineage remain reproducible. Every entry balances independently in one currency.

Prepare cases for contribution, unsettled and settled purchase, corrected purchase, reversal before/after settlement, and every supported diagnostic boundary. Software tests are planned but not executed under the user's standing pause; compilation is permitted. Deployment and feature completion remain outside this assignment.
