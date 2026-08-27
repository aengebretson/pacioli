# LUCA

## What it does

LUCA ingests financial activity from existing systems, normalizes it into a compact canonical ledger, and deterministically derives portfolio state.

```text
FIX ─────────┐
CDM ─────────┤
SWIFT ───────┤
Broker API ──┼──► LUCA
Custodian ───┤       │
Blockchain ──┘       ▼
                  Ledger
                    │
                 Portfolio
                   State
```

The project does **not** require firms to adopt a new interchange standard. FIX, FINOS CDM, SWIFT, broker feeds, custodian files, administrator files, and blockchain data are inputs through adapters. LUCA owns the internal computational representation.

For the deeper architecture and scaling principles, see [docs/design.md](docs/design.md). For phased implementation, ecosystem capabilities, and possible products, see [docs/roadmap.md](docs/roadmap.md).

## Core concepts

- **Source records** — immutable evidence received from an external or internal system.
- **Economic events** — normalized interpretations of economically meaningful activity.
- **Ledger** — ordered, auditable history of economic events with provenance.
- **Projections** — deterministic derivations of positions, cash, lots, settlement, P&L, accounting, and related state.
- **Observations** — external assertions of state from brokers, custodians, administrators, banks, or other systems.
- **Reconciliation** — comparison of projections with observations at transaction, position, account, portfolio, or aggregate levels.

## Planned capabilities

### Ledger and event processing

- Immutable economic-event ledger
- Event provenance and source lineage
- Effective-time and settlement-time semantics
- Corrections, reversals, cancellations, and superseding events
- Replayable portfolio state as of any point in time
- Stable serialization for deterministic reproduction

### Portfolio state

- Positions by account, instrument, strategy, and portfolio
- Settled and unsettled cash
- Receivables and payables
- Tax lots and cost basis
- Settlement obligations and projections
- Realized and unrealized P&L
- Income, fees, financing, and accruals

### Economic events

Initial support will focus on simple cash securities and expand incrementally to:

- Trades and allocations
- Cash movements
- Fees and commissions
- Dividends and interest
- Splits and reverse splits
- Mergers and acquisitions
- Spin-offs and distributions
- Exercises and assignments
- Stock borrow, loan, recalls, and returns
- Financing and collateral events
- FX and multi-currency activity

### Accounting

- Double-entry journal projection from economic events
- Configurable accounting policies
- Trade-date and settlement-date views
- General-ledger and subledger projections
- NAV components and P&L attribution
- Traceability from accounting balances back to source events

### Reconciliation

- Trade reconciliation
- Position reconciliation
- Cash reconciliation
- Settlement reconciliation
- Accounting/NAV reconciliation
- Configurable matching, tolerances, and aggregation keys
- Drill-down from aggregate break to underlying divergent events
- Structured exceptions suitable for human or agent investigation

### Analytics

- Exposure and concentration views
- Portfolio turnover and activity statistics
- P&L explain
- Cash and settlement forecasting
- Event-driven portfolio analytics

### Adapters

Adapters translate external representations into ledger events or observations without making those representations part of the core model.

Planned adapter families include:

- Generic CSV / Parquet
- FIX
- FINOS Common Domain Model (CDM)
- SWIFT / ISO 20022
- Broker and custodian APIs/files
- Fund administrator files
- Blockchain/on-chain transaction data

## Design principles

1. **Deterministic financial core.** Financial truth is computed by explicit code, not probabilistic models.
2. **Events before mutable state.** Portfolio state is derived from economic history rather than treated as the primary source of truth.
3. **Provenance everywhere.** Every derived result should be traceable to source records and transformation rules.
4. **Observations are not events.** A custodian balance or administrator NAV is evidence to reconcile against, not automatically ledger truth.
5. **Interoperability through adapters.** Existing industry formats are accepted rather than replaced.
6. **Small canonical model.** Keep the internal representation compact and computationally useful; preserve source-specific extensions when needed.
7. **Executable semantics.** Correctness should be demonstrated with deterministic replay and conformance tests, not prose specifications alone.
8. **AI outside the ledger.** Agents may classify, map, investigate, and explain, but they do not perform authoritative ledger, accounting, or risk calculations.
9. **Technology-neutral inputs.** Traditional databases, files, APIs, standardized messages, and blockchains are all potential sources.
10. **Library first.** Build a reusable engine before services, dashboards, or agent interfaces.
11. **Scale by construction.** Keep projections side-effect-light, partition-aware, incremental, snapshot-friendly, and batch-oriented so distribution is an execution concern rather than a rewrite.

## Initial milestone

The first release should prove the architecture with the smallest useful domain:

```text
Deposit cash
     │
     ▼
Execute equity trades
     │
     ▼
Append canonical events
     │
     ▼
Replay ledger
     │
     ├──► Positions
     ├──► Cash
     └──► Settlement obligations
                 │
                 ▼
       Compare with observations
                 │
                 ▼
              Breaks
```

### v0.1 target

- `Instrument`
- `Account`
- `Money` / `Quantity`
- `SourceRecord` / provenance
- `EconomicEvent`
- `Ledger`
- position projection
- cash projection
- settlement projection
- state snapshots/checkpoints
- position and cash observations
- generic reconciliation engine
- generic CSV adapter
- synthetic test portfolio with intentional breaks

## Roadmap

The detailed roadmap lives in [docs/roadmap.md](docs/roadmap.md). At a high level:

- **v0.1 — Ledger:** trades, cash, positions, settlement, snapshots
- **v0.2 — Reconciliation:** matching, aggregation, observations, structured breaks
- **v0.3 — Corporate actions:** dividends, splits, mergers, spin-offs
- **v0.4 — Accounting:** journals, lots, accruals, realized/unrealized P&L
- **v0.5 — Securities finance:** borrow, lending, financing, collateral
- **v0.6 — Performance and adapters:** scale-oriented execution plus FIX, CDM, Arrow/Parquet, and selected broker/custodian formats
- **v0.7 — Automation:** agent-assisted mapping, exception investigation, and explanation

Broader applications such as hosted services, web or desktop interfaces, managed reconciliation, and broker-operations products remain possible future products rather than requirements of the core library.

## Non-goals

At least initially, this project is **not**:

- an OMS or execution system
- a pricing library or strategy engine
- a universal financial messaging standard
- a blockchain or distributed ledger
- a fund-administration application
- an AI system that decides financial truth

The objective is narrower: **make investment state reproducible from economic events, and make disagreements with external systems explicit and explainable.**
