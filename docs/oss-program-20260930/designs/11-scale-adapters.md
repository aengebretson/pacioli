# Roadmap item 11 — Scale and external representations of financial algebras

Status: proposed future wave; no implementation worker is assigned by this document. Baseline: OSS snapshot `20e46a6`, 2026-09-30. References: [v0.6 performance](https://github.com/aengebretson/pacioli/blob/main/docs/roadmap.md#v06--performance-and-large-scale-state) and [ecosystem roadmap](https://github.com/aengebretson/pacioli/blob/main/docs/roadmap.md#ecosystem-roadmap).

## Outcome and baseline

Scale the same deterministic financial algebras across local batches and independent partitions, and expose them through demand-led format adapters. Reporting projections retain identical financial results, context, and evidence regardless of host, batch layout, or worker count. Distribution and storage stay outside financial meaning.

The baseline already includes optional reproducible benchmarks for ledger operations, portfolio projections, and reconciliation; synthetic workloads support 10,000, 100,000, and 1,000,000 events. Typed canonical serialization, checkpoint compatibility/application, exact-cash reduction/merge, and a bounded CLI/Python host exist. They do not constitute a general distributed runtime, columnar engine, generic adapter framework, or arbitrary partition-merge contract.

## Phased increments

1. **Measure current execution.** Expand existing workloads to lifecycle resolution, correction invalidation, checkpoint loading/application, and journal projection. Record correctness, hardware, compiler, flags, dataset, repetitions, memory method, and revision.
2. **Independent partition execution.** Introduce explicit projection-specific partition plans, complete keys, overlap detection, deterministic result ordering, and compatible merge operations. Start with disjoint account partitions for supported cash/equity workloads. Preserve ordered replay inside each partition and route cross-partition dependencies explicitly.
3. **Incremental/batch optimization.** Profile before changing algorithms. Improve selection, reuse, and memory layout behind existing financial contracts; extend checkpoint support only where full replay equivalence is proven. Add columnar batch representations without redefining arithmetic or lifecycle order.
4. **Adapters by actual workflow.** Reuse item 7 CSV normalization first. Add Arrow/Parquet interchange if measured workloads justify it; then select one FIX, CDM, ISO 20022, or broker/custodian mapping from real authorized sample requirements. Each adapter owns source parsing and normalization provenance, never core financial calculations.

## Algebra and representation semantics

Parallelism follows proved algebraic laws. Exact cash reduction is associative/commutative only for compatible keys/context and the documented checked-arithmetic domain; alternate reduction trees must not silently alter overflow behavior. Ordered lifecycle, lot, and dependent corporate-action folds cannot be arbitrarily regrouped. Complete settlement keys preserve payable/receivable direction.

Canonical domain serialization remains the identity contract. A Parquet file or Arrow buffer is an external representation, not automatically canonical bytes. Preserve decimal scale, currency, timestamps/dates, null meaning, stable identities, lineage, and ordering fields explicitly. Lossy conversions and unknown variants return diagnostics. Input observations remain separate from authoritative events throughout import and reporting.

## Dependencies and parallel boundaries

Depend on O1 installed consumers, O2/O3 replay/checkpoint contracts, O5 operation laws, and item 7 normalization boundaries. Benchmark expansion and an independently specified adapter can run in parallel. Partition planning must wait for the relevant projection contract; cross-instrument actions and collateral may require broader partitions. Infrastructure hosts consume reviewed outputs without embedding alternative arithmetic.

## Independent acceptance criteria

Compare full, incremental, varied-batch, and varied-worker outputs, hashes, and lineage on fixed fixtures. Reject overlapping partitions and incompatible contexts. Demonstrate reordered-dependent-event counterexamples. Adapter round trips preserve domain values and evidence; malformed decimals and unsupported schemas fail. Publish reproducible before/after benchmark results and memory methodology; require measured benefit with no semantic regression before accepting an optimization.

## Deferred decisions

No Kafka, cluster scheduler, database, plugin ABI, universal schema mapper, global partition key, performance SLA, or broad protocol rollout is selected. Choose integrations and throughput targets only after concrete consumer requirements and measured costs exist.
