# LUCA Roadmap

LUCA should grow outward from a small deterministic ledger core. Capabilities belong in one of three rings:

1. **Core** — defines financial truth and reproducible portfolio state.
2. **Ecosystem** — connects LUCA to external formats, runtimes, and languages.
3. **Applications/products** — use LUCA to solve workflows; these are not core requirements.

## Core roadmap

### v0.1 — Ledger and basic state

Prove the fundamental model with cash and simple equity activity.

- Account, instrument, money, quantity
- Source records and provenance
- Canonical economic events
- Immutable ordered ledger
- Effective-time and settlement-time semantics
- Deposit and withdrawal events
- Equity trades, fills, cancellations, and corrections
- Position projection
- Settled/unsettled cash projection
- Settlement obligations
- Full replay and deterministic output
- Initial state snapshots/checkpoints
- Synthetic conformance fixtures

### v0.2 — Reconciliation

Make reconciliation a generic comparison between deterministic projections and external observations.

- Position observations
- Cash observations
- Trade observations
- Matching policies
- Tolerances
- Aggregation keys
- Structured breaks/exceptions
- Drill-down from aggregate break to source events
- Batch reconciliation
- Parallel partitioning by appropriate domain keys

### v0.3 — Asset servicing / corporate actions

Extend the event model beyond ordinary trades.

- Dividends and interest
- Splits and reverse splits
- Mergers
- Spin-offs and distributions
- Cash-in-lieu and fractional handling
- Elections and entitlements where applicable
- Corporate-action corrections
- Conformance scenarios for complex state transitions

### v0.4 — Portfolio accounting

Treat accounting as a deterministic projection over the same economic events.

- Journal projection
- Lots and cost basis
- Realized/unrealized P&L
- Accruals
- Income and expenses
- Trade-date and settlement-date views
- General-ledger/subledger projections
- NAV components
- Traceability from balances to events

### v0.5 — Securities finance

Add brokerage/prime-brokerage economic events.

- Stock borrow and loan
- Recalls and returns
- Financing accruals
- Borrow fees/rebates
- Collateral movements
- Margin-related observations
- Securities-finance reconciliation

### v0.6 — Performance and large-scale state

Harden the compute model for very large datasets without changing financial semantics.

- Explicit partition-aware APIs
- Efficient incremental replay
- Snapshot versioning and rebuilds
- Batch/columnar execution paths
- Reproducible performance benchmark suite
- Parallel scaling tests
- Memory and throughput targets

## Ecosystem roadmap

These capabilities connect LUCA to the outside world but do not define the core model.

### Data and protocol adapters

- Generic CSV
- Parquet
- Apache Arrow
- FIX
- FINOS Common Domain Model (CDM)
- SWIFT / ISO 20022
- Selected broker/custodian formats
- Fund-administrator files
- Blockchain/on-chain activity

### Bindings and execution hosts

- C++ library API
- CLI
- Python bindings
- C ABI where useful
- REST/gRPC service host if demanded by integrations
- WebAssembly only if a concrete local/browser use case emerges

### Agent integration

Agents sit outside authoritative financial calculations.

- Schema and source mapping assistance
- Exception investigation
- Break explanation
- Evidence gathering
- Operational workflow orchestration
- Human approval at consequential boundaries

## Potential applications and commercial products

These should be built only when a real user workflow justifies them.

- Managed reconciliation service
- Broker operations platform
- Portfolio-accounting service
- Exception-management UI
- Agent-assisted operations console
- Customer-facing API platform
- Hosted portfolio-state service
- Broker/custodian integration service
- Desktop or web applications

The open-source core should remain useful without any of these products.

## Architectural guardrails

The roadmap should preserve the following constraints from the beginning:

- deterministic financial core
- no hidden database I/O in projections
- immutable/versioned event inputs
- explicit event ordering and causality
- incremental processing plus full replay
- versioned snapshots
- partition-aware APIs
- batch-oriented processing
- adapters outside the core model
- storage and distribution outside financial semantics
- conformance tests for executable behavior

## Near-term implementation sequence

The next engineering work should remain deliberately small:

1. Define source provenance, account, instrument, money, and quantity types.
2. Define the minimal economic-event representation without over-modeling the entire financial industry.
3. Implement an append-only in-memory ledger.
4. Implement deposit and equity-trade events.
5. Project position, cash, and settlement state.
6. Add snapshots and verify replay from snapshot + incremental events equals full replay.
7. Add position/cash observations and generic reconciliation.
8. Add synthetic conformance tests and a first performance benchmark.

Only after these semantics are stable should broader adapters, cloud execution, UI, or agent layers become active engineering work.
