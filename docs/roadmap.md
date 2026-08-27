# LUCA Roadmap

LUCA should grow outward from a small deterministic ledger core. Capabilities belong in one of three rings:

1. **Core** — defines financial truth and reproducible portfolio state.
2. **Ecosystem** — connects LUCA to external formats, runtimes, and languages.
3. **Applications/products** — use LUCA to solve workflows; these are not core requirements.

The version milestones below describe capability groups, not rigid release gates. Engineering slices may establish cross-cutting foundations or introduce a narrow part of a later capability when that work reduces architectural risk for the whole project.

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

## Current baseline

The repository has already implemented a meaningful portion of the original near-term sequence:

- strong account, instrument, currency, money, quantity, source-record, and provenance values;
- cash-movement and equity-trade events;
- an append-only in-memory ledger with deterministic ordering;
- position projection;
- settled-cash projection;
- open-settlement-obligation projection;
- exact position and settled-cash reconciliation;
- unit and executable conformance tests;
- a reproducible benchmark suite.

The next work should no longer repeat that original bootstrap checklist. It should turn the existing primitives into a consumable engine, close foundational lifecycle/replay gaps, and prove the accounting thesis.

## Current implementation program

The next four slices are the active engineering sequence.

### Slice 1 — LUCA identity and package

Turn the repository into a deliberate open-source C++ dependency.

- establish LUCA as the single canonical project identity;
- define domain-oriented `luca::...` CMake targets;
- support both `add_subdirectory` and installed `find_package` consumption;
- prevent tests, examples, and benchmarks from polluting parent builds;
- add install/export rules and an external package-consumer test;
- add one end-to-end public-API example;
- establish Linux GCC/Clang and Windows MSVC CI;
- prepare a first preview release and repository rename.

Detailed design: [Slice 1 — LUCA identity and package](slices/01-identity-and-package.md).

### Slice 2 — Event lifecycle

Define immutable lifecycle semantics before the event domain expands.

- cancellation;
- reversal;
- correction;
- supersession;
- causal lineage between events;
- deterministic replay after late lifecycle events;
- conformance scenarios that prove positions, cash, settlement, and provenance after lifecycle changes.

The ledger must never silently mutate accepted historical facts to implement a correction.

### Slice 3 — Serialization and checkpoints

Make replay and derived state portable, hashable, and incrementally reproducible.

- versioned canonical serialization outside domain value objects;
- deterministic event and projection representations;
- input and state hashes;
- position, cash, and settlement checkpoints;
- projection version and event-watermark metadata;
- conformance tests proving full replay equals checkpoint plus incremental events.

Storage technology remains outside financial semantics.

### Slice 4 — Accounting foundations

Prove that the same event history can produce balanced, traceable accounting output.

- journal-entry and journal-line value types;
- balanced debit/credit invariants;
- a narrow accounting-policy interface;
- journal projection for cash movements and equity trades;
- trade-date and settlement-date views;
- full lineage from journal line to economic event to source-record provenance;
- conformance fixtures covering a cash contribution, an equity purchase, settlement state, and balanced journals.

This slice begins the v0.4 accounting capability but does not attempt lots, tax accounting, complete P&L, NAV production, or universal charts of accounts.

## Program completion criteria

The four-slice program is complete when:

- an unfamiliar C++ developer can install and consume LUCA through documented public targets;
- LUCA Enterprise can pin and build LUCA without using internal headers or source files;
- event corrections and reversals have explicit immutable semantics;
- deterministic serialized inputs and state can be hashed and replayed;
- incremental replay from a checkpoint is equivalent to full replay;
- cash and equity activity produce positions, cash, settlement obligations, reconciliation breaks, and balanced journals from one authoritative event history;
- all behavior is demonstrated through reusable conformance fixtures.

Only after these foundations are stable should broader adapters, cloud execution, extensive UI, distributed orchestration, or agent layers become active open-source engineering priorities.