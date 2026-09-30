# Roadmap item 10 — Securities-finance algebras and obligation projections

Status: proposed future wave; no implementation worker is assigned by this document. Baseline: OSS snapshot `20e46a6`, 2026-09-30. Roadmap reference: [v0.5 securities finance](https://github.com/aengebretson/pacioli/blob/main/docs/roadmap.md#v05--securities-finance).

## Outcome and baseline

Represent loans, borrows, recalls, returns, financing charges, and collateral as immutable typed economic activity. Derive open contracts, contractual obligations, collateral, accrual, cash, and reconciliation reports through explicit financial algebras and projections. Custody movement does not imply ownership transfer.

The baseline supports cash movements, equity trades, lifecycle resolution, portfolio state, exact cash/position reconciliation, portable checkpoints, and narrow trade-date journals. There are no securities-finance event families, contracts, collateral allocations, borrow-fee rules, or margin models. 

## Phased increments

1. **Contract and quantity lifecycle.** Define one fixed-term, single-instrument loan/borrow contract, explicit party roles, account/book scope, quantity, opening/closing dates, and settlement evidence. Add opening, partial return, full return, and recall events with causal references.
2. **Financing accrual.** Add supplied rate schedules, explicit day-count/calendar inputs, accrual boundaries, currency, and rounding stage. Derive gross fee/rebate obligations and distinguish expected payment from cash evidence. Rate corrections retain old evidence and rebuild affected periods.
3. **Collateral movements.** Model posted/received collateral and its contract allocations separately from ownership and accounting recognition. Support a narrow cash-collateral case first. Require valuation and haircut evidence for securities collateral.
4. **Accounting and reconciliation.** Map reviewed events/accruals to balanced journals through O4 policies. Compare loan balances, returns, fees, and collateral with external counterparty observations using typed matching and tolerance policies.

## Algebra and policy semantics

Contract transitions are ordered folds keyed by account/book, counterparty, and contract. Partial returns consume open quantity and must not exceed eligible outstanding quantity under the first policy. Recalls are requests with explicit status; they do not imply return or settlement. Corrections use O2 lifecycle rules, not mutation of a running balance.

Accrual mapping consumes a complete dated rate interval and contract-state interval. Only disjoint, compatible intervals can reduce into a charge total; overlap is rejected to prevent double counting. Money reductions preserve currency, contract, fee kind, and policy context. Cross-contract netting is a separate legal/policy operation. Collateral allocated across contracts requires a broader partition boundary and cannot be independently counted by each contract worker.

Each result identifies economic, knowledge, and settlement cutoffs; event/source lineage; valuation/rate evidence; and engine, projection, and policy versions. Reports remain reproducible derived views. Projections perform no hidden I/O.

## Dependencies and parallel boundaries

Depend on O2/O3 lifecycle and schema/checkpoint extension, O4 accounting policy, O5 composition, and item 7 richer reconciliation. Item 9 accrual/valuation primitives should be reused where semantics match. Contract fixtures, accrual policy examples, and observation schemas can be drafted independently. Shared event variants and serializers require coordinated ownership; collateral allocation follows the reviewed contract boundary.

## Independent acceptance criteria

Hand-calculated fixtures cover opening, partial return, recall without return, full closure, and a late correction. Fee totals equal daily interval calculations with no duplicate days. Collateral totals reconcile without double allocation. Unsupported negative outstanding quantity, overlapping schedules, absent rates, and currency mismatch fail explicitly. Full replay and supported checkpoint continuation agree; corrections force rebuild where necessary. Every reported obligation links to immutable evidence.

## Deferred decisions

Open-ended agreements, manufactured dividends, term renegotiation, substitutions, rehypothecation, default waterfalls, margin calls, legal netting, and jurisdiction-specific accounting require separate policies. No production agreement interpretation or margin methodology is implied by the first fixtures.
