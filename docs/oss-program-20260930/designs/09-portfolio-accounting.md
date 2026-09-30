# Roadmap item 9 — Portfolio-accounting algebras and reporting projections

Status: proposed future wave; no implementation worker is assigned by this document. Baseline: OSS snapshot `20e46a6`, 2026-09-30. Roadmap reference: [v0.4 portfolio accounting](https://github.com/aengebretson/pacioli/blob/main/docs/roadmap.md#v04--portfolio-accounting).

## Outcome and baseline

Extend the existing accounting foundation into explicit lot, cost-basis, P&L, accrual, subledger, and NAV-component projections. All financial meaning stays in typed, versioned OSS algebras. Reporting selects and aggregates their results while preserving the event history and policy provenance.

The baseline provides immutable journal value types and `project_trade_date_journals` under `luca::ledger`. Its bounded fixture policy covers USD contributions, purchases, and exact equity reversals; it does not implement general sales, withdrawals, lots, valuation, tax, accruals, or NAV. Extend reviewed public boundaries before relocating headers.

## Phased increments

1. **Lots and ordinary disposals.** Add typed acquisition lots, deterministic FIFO allocation, remaining quantity/basis, and realized P&L for ordinary equity sales. Explicitly reject short sales and insufficient inventory initially. Preserve allocation lineage from disposal to acquisition events and evidence.
2. **Valuation and unrealized P&L.** Accept explicitly supplied, versioned price observations with valuation date and currency. Produce valuation and unrealized-P&L projections. Missing/stale prices and unsupported FX return named diagnostics, rather than zero values or live lookups.
3. **Accrual and income/expense.** Add narrow daily accrual policies with supplied schedules, rates, day-count conventions, and recognition dates. Separate economic obligation, accrual estimate, journal recognition, and cash receipt/payment.
4. **Balances and NAV components.** Reduce validated journals to subledger balances and expose clearly named NAV components with completeness status. Publish a complete NAV only after its valuation, accrual, liability, FX, and policy coverage is explicitly defined.

## Algebra and policy semantics

Lot allocation is an ordered state fold, not an additive summary. Acquisition/disposal order, allocation method, and economic/knowledge cutoffs determine its result. Corrections trigger affected-state replay; a negative input is not a universal inverse. Per-lot basis allocation must conserve total acquisition cost under an explicit residual-allocation rule. Quantity, price, rate, money, and currency remain distinct types.

Journal mapping consumes resolved events and allocation/valuation outputs through typed ports. Balances are checked exact reductions by book/account/currency; group only compatible contexts and policy versions. Reporting projections compose balances and analytical results but cannot silently net currencies, change accounting recognition, or promote external marks into ledger events. Projection identity includes the price dataset and policy versions as well as event inputs.

## Dependencies and parallel boundaries

O4 must establish policy extension and trade/settlement behavior; O2/O3 provide causal resolution and invalidation. O5 defines safe composition. Lot fixtures and price-input contracts can progress separately once reviewed. Item 8 supplies corporate-action events for later basis transformations. A single owner coordinates allocation semantics shared by realized P&L and journals; separate reporting work can consume stable output types.

## Independent acceptance criteria

A hand-calculated two-acquisition/one-disposal fixture proves FIFO allocation, conserved cost basis, realized P&L, remaining positions, and balanced journals. A supplied-price fixture proves unrealized P&L. A late acquisition correction changes dependent allocations while preserving old-cutoff results. Invalid contexts, absent marks, mixed currencies, and unsupported shorts fail explicitly. Independent consumers reproduce report rows, totals, and source lineage through installed public APIs.

## Deferred decisions

Average cost, specific identification, short-lot treatment, tax jurisdiction, GAAP/IFRS policy, functional currency, FX translation, period close/reopen, and production NAV certification need separate designs. No fixture chart of accounts is silently promoted to a universal chart.
