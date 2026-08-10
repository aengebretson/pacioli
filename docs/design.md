# LUCA Design

LUCA is a deterministic investment ledger and portfolio-state engine. It ingests heterogeneous source records, normalizes economically meaningful activity into a compact canonical event model, and derives reproducible portfolio state.

The design goal is not to build a distributed system first. The goal is to make the financial core **partitionable, deterministic, replayable, and side-effect-light** so the same computation can run efficiently in one process, a batch job, or many distributed workers.

## Architecture

```text
FIX ─────────┐
CDM ─────────┤
SWIFT ───────┤
Broker API ──┼──► LUCA adapters
Custodian ───┤          │
Blockchain ──┘          ▼
                    Source records
                          │
                          ▼
                   Economic events
                          │
                          ▼
                       Ledger
                          │
                          ▼
                    Projections
              ┌───────────┼───────────┐
              ▼           ▼           ▼
          Positions      Cash      Accounting
              │           │           │
              └───────────┼───────────┘
                          ▼
                    Portfolio state
                          │
                          ▼
                   Reconciliation
                          │
                          ▼
                External observations
```

FINOS CDM, FIX, SWIFT, broker files, custodian feeds, administrator files, and blockchain events are adapters. They are not the internal model.

## Core model

LUCA separates three layers of truth:

1. **Source record** — what an external or internal system reported. Preserve it unchanged.
2. **Canonical economic event** — LUCA's normalized interpretation of economically meaningful activity.
3. **Derived state** — positions, cash, settlement, lots, journals, P&L, and other state computed deterministically from events.

A source record is immutable evidence identity and audit context, not a payload
container: raw bytes remain in adapter-managed or external storage. Provenance
links canonical data to one or more source-record identifiers and records the
name, version, and small optional audit metadata of the normalization that
produced it. Neither type defines storage or serialization behavior.

External balances and snapshots are **observations**, not automatically ledger truth. They are reconciled against derived state.

## Deterministic computation

Financial calculations should behave like pure transformations wherever practical:

```text
versioned input events
        +
projection rules
        ▼
deterministic output state
```

Avoid architectures where calculations repeatedly fetch and mutate database rows. Financial logic should receive the data it needs explicitly rather than performing hidden I/O.

This provides four important properties:

- reproducibility
- testability
- caching
- parallel and distributed execution

## Partitioning and scale

The normal scaling model is:

> **parallel across independent partitions, ordered replay within a partition.**

Natural partition keys may include:

- portfolio
- account
- legal entity
- strategy or book
- instrument
- currency

The correct key depends on the projection. Position calculations may partition very finely; cash, NAV, margin, or cross-instrument events may require broader aggregation.

A future distributed worker should not own business state. It should receive explicit versioned inputs, for example:

```text
Projection job
  portfolio/account partition
  projection type
  snapshot identifier
  event range or watermark
  projection version
```

and return a deterministic result.

## Ordering and causality

Event order is financially meaningful. Buys, sells, corrections, settlements, corporate actions, and reversals cannot be replayed arbitrarily.

LUCA must define stable ordering semantics including, where needed:

- economic/effective time
- processing time
- settlement time
- causal relationships
- correction/reversal lineage
- deterministic tie-breaking

The engine should parallelize only where those semantics permit it.

## Incremental state and snapshots

Pure event replay from inception is correct but can become impractical at scale. LUCA should support both full replay and versioned state checkpoints.

Normal operation should be incremental:

```text
State(t-1)
+
new events
    ▼
State(t)
```

A snapshot should record enough metadata to be independently verified and rebuilt, such as:

- portfolio or partition key
- projection version
- input event watermark
- as-of time
- state hash

If projection logic changes, snapshots can be rebuilt from immutable events.

## Three execution modes

LUCA should support the same semantics across three modes.

### Incremental processing

Use a prior verified state plus newly arrived events. This is the normal operational path.

### Full replay

Recompute state from immutable event history for audit, corrections, policy changes, validation, or rebuilding snapshots.

### Analytical projection

Run P&L attribution, exposure, historical analysis, or other analytics over event/state data without coupling those calculations to transactional persistence.

## Batch and columnar processing

The engine should avoid record-by-record ORM-style access in hot paths. Large event sets should be processable in batches using compact memory layouts.

Arrow and Parquet belong in the ecosystem because they can provide efficient in-memory and durable representations, but they are adapters/storage formats rather than LUCA's financial semantics.

## Accounting and reconciliation

Accounting should be a projection over economic events. Individual events can often generate journals independently, while balances are reductions over those entries.

Reconciliation should be generic over projections and observations rather than implemented as unrelated trade, position, cash, and NAV applications.

Conceptually:

```text
reconcile(
  projection(events),
  observation,
  matching_policy
)
```

Reconciliation should support comparison at different aggregation levels and drill down from an aggregate break to the first divergent events or assumptions.

## Performance principles

1. **No hidden I/O inside financial calculations.**
2. **Immutable, versioned inputs.**
3. **Explicit partition keys and ordering semantics.**
4. **Incremental processing with deterministic full replay.**
5. **Versioned snapshots/checkpoints.**
6. **Batch-oriented processing for large datasets.**
7. **Storage is outside the financial semantics.**
8. **Distribution wraps the core; it does not live inside it.**
9. **One financial implementation across local, batch, and distributed execution.**
10. **Measure performance with reproducible benchmarks and conformance tests.**

## What not to build yet

The open-source core should not require Kafka, Kubernetes, a distributed database, service mesh, or remote RPC between ledger components. Those may become deployment choices later.

A fast, deterministic single-process C++ engine is the best foundation for distributed execution because the distributed layer can simply schedule independent instances of the same computation.

## Performance roadmap

As the domain grows, publish reproducible benchmark scenarios measuring:

- event ingest throughput
- replay throughput
- incremental update latency
- reconciliation throughput
- snapshot load/write time
- memory per event/state unit
- parallel scaling efficiency

The long-term performance objective is simple:

> **financial semantics rigorous enough for accounting, implemented like a modern compute engine.**
