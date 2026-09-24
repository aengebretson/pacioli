# Executable transformation and composition contract

Status: executable design contract for O5-T01 plus the bounded exact-cash C++
reduction, lineage-bearing exact comparison, and standalone execution host
implemented by O5-T02 through O5-T04. The JSON fixtures and their
dependency-free validators define the wider portable semantic vocabulary for
design review. The exact-cash APIs and host are not a generic composition
runtime, canonical wire format, checkpoint format, plugin ABI, or second
implementation of LUCA projections.

## Purpose and boundary

LUCA already has deterministic ledger ordering, cash/position/settlement
projections, and exact reconciliation. This increment names the different kinds
of work those APIs perform and states when results may be composed or merged.
It does not wrap the current APIs in a generic runtime.

The smallest vocabulary is:

- **normalization** interprets immutable source evidence as a typed canonical
  record and retains source provenance;
- **map** converts one typed value to another without cross-record state;
- **ordered fold** applies typed inputs to state in a declared total order;
- **reduction** combines compatible values with only the algebraic laws that
  the operation explicitly proves; and
- **comparison** compares an authoritative projection with separate,
  non-authoritative observations and produces breaks.

Lifecycle resolution is an ordered fold between normalization and portfolio
projection. Raw lifecycle records are not economic events ready for projection.
The O2 contract selects one active payload per economic identity at a knowledge
cutoff, then projections use that resolved set at the economic and settlement
cutoffs. Corrections and cancellations replace or suppress a chain head; a
reversal is a separate explicit event. None of these facts supplies a general
mathematical inverse.

All inputs, policies, contexts, and evidence are supplied explicitly. A
deterministic operation performs no filesystem, database, network, authorization,
or scheduling work. Execution hosts own those concerns.

## Existing-interface inventory

The table describes the public headers in this checkout. “Semantic
decomposition” means that the fixture vocabulary can describe part of an
existing function; it does not claim a new callable API exists.

| Boundary | Existing public interface | Classification in this contract | Current limits |
| --- | --- | --- | --- |
| Source evidence | `SourceRecord`, `PayloadHash`, and `Provenance::create` | normalization boundary values | No generic public normalizer or adapter policy interface exists. Raw payload bytes and IO remain external. |
| Canonical event construction | `EventHeader::create`, `CashMovement::create`, `EquityTrade::create` | normalization output validation | The closed `EconomicEvent` variant contains cash movements and equity trades only. These constructors do not normalize an external format. |
| Economic selection/order | `economic_entries`, `economic_entries_through`, and `economic_entries_between` | ordered-input preparation | Order is `(effective_at, LedgerSequence)`. The sequence is ledger-local and only a tie-breaker. |
| Scalar valuation | `value(Quantity, Price, Currency, RoundingMode)` | map | Produces scale-6 `Money`; default rounding is half-even. Overflow is a `ValueError`. It does not carry event lineage by itself. |
| Position state | `project_positions(span<LedgerEntry>, Timestamp)` | ordered fold with an embedded event-to-delta map and checked aggregation | Equity trades add scale-8 quantity by `(account, instrument)`; zeros are omitted. It returns `quantity_overflow`. It is not lifecycle-aware yet. |
| Settled cash | `project_cash(span<LedgerEntry>, CashProjectionContext)` | ordered fold with embedded mapping/aggregation | Cash is keyed by `(account, currency)`. Trade cash is `-(quantity × price)` only when settlement-eligible; valuation is half-even to scale 6. It returns `valuation_overflow` or `amount_overflow`. |
| Open settlement | `project_settlement_obligations(span<LedgerEntry>, SettlementProjectionContext)` | ordered fold with embedded mapping/aggregation | Positive magnitudes are keyed by `(account, settlement_date, currency, direction)`. Payables and receivables are not netted. It returns `valuation_overflow` or `amount_overflow`. |
| Exact addition | `Quantity::add`, `Money::add`, and `reduce_exact_cash`/`merge_exact_cash` in `luca/portfolio/exact_cash_reduction.hpp` | compatible reduction primitives | The public cash reducer is deliberately limited to one explicit `(account, currency)` key, `money` unit, and `(account, currency)` partition declaration. It delegates every sum to `Money::add`; there is no public generic reducer. |
| Position comparison | `reconcile_positions(expected, observed, PositionReconciliationContext)` | comparison | Exact shared `as_of`; detects duplicate observations, time mismatch, overflow, and missing/unexpected/mismatched values. `Position` and `PositionBreak` do not retain projection provenance; a break retains observation provenance only when an observation exists. |
| Settled-cash comparison | `reconcile_cash(expected, observed, CashReconciliationContext)` | comparison | Exact shared economic and settlement cutoffs; detects duplicate observations, both context mismatches, overflow, and missing/unexpected/mismatched values. `CashBalance` and `CashBreak` do not retain projection provenance; a break retains observation provenance only when an observation exists. |
| Lineage-bearing exact cash comparison | `compare_exact_cash(ExactCashComparisonContract, projected, observed)` in `luca/reconciliation/exact_cash_comparison.hpp` | comparison | Compares `ExactCashReductionResult` values with separate `CashObservation` evidence by complete `(account, currency)` key. The result records its operation/policy/context trace; each break retains the applicable projection and observation in distinct roles. It adds no FX, tolerance, or authority-changing behavior. |
| Lifecycle acceptance and resolution | `LifecycleRecordDraft::{originate,correct,cancel,reverse}` and `LifecycleLedger::{accept,accept_batch,resolve}` in `luca/lifecycle.hpp` | ordered fold before all affected projections | This is a public in-memory C++ API. Acceptance validates immutable causal records and assigns lifecycle sequences; `resolve(recorded_through, economic_as_of)` returns knowledge-selected chains and active payloads ordered by `(effective_at, acceptance_sequence)`. Existing position, cash, and settlement projection functions do not yet consume `LifecycleResolution`. |
| Journals/accounting | none in the current checkout | future map and reduction boundaries | Journal types and accounting-policy interfaces belong to O4. This contract does not invent their signatures or decide accounting policy. |

The public lifecycle increment is narrower than the fixture composition shown
here: it implements causal acceptance and two-cutoff resolution, but not the
downstream projection adapters or composed-result lineage vocabulary. The
current projection functions accept entries in any input order because they
first request the ledger's canonical economic view. That convenience does not
make the financial transition commutative: the evaluation order remains part of
the contract, and lifecycle records must be resolved before that view exists.

## Typed operation declaration

Every operation demonstrated in
`tests/conformance/transformation-contract/*.json` declares the following
fields. Field names are conformance vocabulary, not promised production
serialization.

| Declaration | Meaning |
| --- | --- |
| `id`, `classification`, `operation_version` | Stable semantic identity, one of the five classes above, and the version of the calculation. |
| `input_ports`, `output_port` | Named types plus units and currency. A multi-input comparison declares the projection and observation ports separately. |
| `policy.id`, `policy.version` | The named financial or interpretation policy used by this operation. Different operations may use different policy identities; each result records its own. |
| `evaluation_context` | Context identity, engine version, inclusive `recorded_through`, inclusive `economic_as_of`, and independent `settlement_as_of_date`. A pure reducer still records the context in which its inputs are meaningful. |
| `ordering` | Whether order is required, the total-order keys, and whether arbitrary reordering is equivalent or rejected. |
| `partitioning` | Whether partitioned execution is supported, the complete financial keys, and the compatible merge operation. `supported: false` is meaningful and must not be ignored by a host. |
| `rounding` | Mode, output scale, and the exact arithmetic stage at which rounding occurs. `none` and `not_applicable` are explicit. |
| `errors` | Stable semantic categories that callers can handle without parsing prose. Implementations may attach paths and identifiers. |
| `lineage` | Required input identity fields and identities/versions that the result emits. |
| `laws` | Separate declarations for identity, associativity, commutativity, invertibility, and distributivity, plus the domain on which a proof applies. |

An operation returns either its declared output or a declared diagnostic. It
must not return a partial financial result as though it were successful after an
overflow, incompatible context, missing causal record, or dimensional mismatch.

### Composition compatibility

For an edge `A.output -> B.input`, the first contract requires all of the
following:

1. The output and selected input port types are equal. `CashBalanceSet` is not
   `PositionDeltaSet` merely because both contain fixed-point numbers.
2. Units are equal. Money, quantity, price, rate, and obligation direction are
   not interchangeable.
3. Currency declarations are equal. Cross-currency composition requires a
   separate, explicit FX operation and versioned policy; none exists here.
4. The complete evaluation contexts are equal. Matching context names with
   different economic, knowledge, settlement, or engine versions is not enough.
5. A projection port that requires `ResolvedEconomicEventSet` cannot consume
   `RawLifecycleRecordSet`.
6. Any merge uses every declared partition key and the declared merge operation.
   Dropping `direction` from settlement obligations would silently net a payable
   with a receivable and is rejected.

The portable categories exercised by negative fixtures are
`operation_type_mismatch`, `unit_mismatch`, `currency_mismatch`,
`context_mismatch`, `unresolved_lifecycle_input`, and
`partition_key_mismatch`. These categories describe why composition is unsafe;
they do not prescribe a C++ error enum for a later implementation.

Policy versions are traced per operation rather than required to be identical
across unlike operations. Reusing a prior output for the *same* operation does
require the same operation, engine, policy, and context versions. A change to
any of them follows the invalidation rules below.

## Ordering, partitions, and actual laws

### Exact cash reduction

The fixture operation `reduce.cash.exact` combines `Money` values only for one
`(account, currency)` key. It exposes scale-6 zero as identity and claims
associativity and commutativity only on the declared domain: same currency and
key, exact fixed-point values, and every checked intermediate sum representable
as `int64`. Currency mismatch and overflow remain errors, so the claim is not a
universal algebra over arbitrary JSON decimals or all `Money` values.

Within that domain the fixture proves:

```text
full:        1000.000000 + (-250.000000) + 50.000000 = 800.000000 USD
incremental: (1000.000000 + -250.000000) + 50.000000 = 800.000000 USD
partitioned: partial(750.000000) + partial(50.000000) = 800.000000 USD
identity:    800.000000 + 0.000000 = 800.000000 USD
```

The partials may be calculated independently and merged because this reduction
declares and demonstrates the compatible merge. A host partition identifier is
operational metadata and is not part of the result. Financial merge keys and
lineage are part of the result.

The public C++ implementation exposes validated
`ExactCashReductionPolicy`, `ExactCashEvaluationContext`,
`ExactCashPartitioning`, `ExactCashReductionContract`, and `ExactCashPartial`
values. `reduce_exact_cash` combines already-produced partials;
`merge_exact_cash` combines compatible reduction results; and
`exact_cash_zero` constructs the identity only from an explicit compatible
contract. The result retains the key, unit, partition declaration, operation
identity/version, policy identity/version, all three evaluation cutoffs plus
context and engine identities, exact amount, and event/source lineage.

All identifiers are non-empty tokens without ASCII whitespace or control
characters. A context is incomplete when its context or engine identity is
absent; its recorded, economic, and settlement cutoffs are mandatory typed
arguments. A non-identity partial requires at least one event ID and one source
record ID. Event and source identifiers are sorted lexically in results so
input and partition order do not affect lineage. Duplicate event IDs within or
across partials return `duplicate_event_lineage` before arithmetic because the
same event appearing twice would make contribution multiplicity ambiguous.
Repeated source-record IDs are valid when one evidence record supports more
than one event; they are retained once in the sorted source-evidence set.

Compatibility failures have stable categories for account, currency,
operation version, policy identity, policy version, complete context, unit, and
partition-key mismatches. Unsupported zero contracts fail with `unit_mismatch`
or `partition_key_mismatch`. Checked overflow returns `amount_overflow` and no
result. The reduction does not round and calls the existing `Money::add` for
each checked addition.

Although scalar signed addition has an additive opposite on a representable
domain, this operation deliberately makes no `invertibility` claim. A negative
cash amount does not prove that a source event is a valid lifecycle reversal,
and removing a previously aggregated value still requires event/lifecycle
evidence and invalidation.

### Lifecycle resolution and portfolio folds

The equity fixture has an original trade of `100 × 50` and a late correction to
`80 × 55`. Normalization retains both immutable raw records. O2 lifecycle
resolution selects the correction as the active payload while retaining both
source records in lineage. At the fixture context:

```text
position                         = 80.00000000 MSFT
trade gross                      = 80.00000000 × 55.00000000
                                  = 4400.000000 USD (half-even, scale 6)
settled cash before 2026-06-04   = no trade-cash balance
open settlement before 2026-06-04 = 4400.000000 USD payable
```

The ordered fold's valid record order is origin then correction. The
counterexample presents correction then origin. That permutation puts the
correction's `2026-06-05` recorded time before the origin's `2026-06-02`
recorded time. Public `LifecycleLedger::accept_batch` therefore returns
`deterministic_ordering` before evaluating causal availability; it cannot obtain
the resolved result by arbitrary reordering. The lifecycle fold
therefore claims no commutativity, associativity, identity, invertibility, or
distributivity, and it does not permit a raw chain to be split and merged.

The fixture shows a semantic event-to-position map and exact position reduction
so the type boundary can be reviewed. Those names are not new public C++ APIs;
the current `project_positions` function embeds both steps. T01 makes no
reusable law claim for that decomposition. Likewise, the current cash and
settlement functions remain ordered folds. Their disjoint financial keys are
safe parallel boundaries only after lifecycle resolution and only with the
complete context; this increment does not add a partitioned API.

For settlement output, the complete key is:

```text
(account, settlement_date, currency, direction)
```

The negative fixture uses otherwise equal payable and receivable keys and shows
that merging on `(account, settlement_date, currency)` is invalid. LUCA's
current projection intentionally keeps their positive magnitudes separate.

### Lineage-bearing exact comparison is not a reduction

`compare.cash.exact` receives projected cash and external observations through
different typed ports. With projected cash `800.000000 USD` and an observed
balance `790.000000 USD`, it produces one `amount_mismatch` whose existing LUCA
sign convention is:

```text
difference = observed - expected = 790.000000 - 800.000000
           = -10.000000 USD
```

The public `ExactCashComparisonPolicy` and `ExactCashComparisonContract` require
complete token identities and reuse the reducer's `ExactCashEvaluationContext`.
Consequently every `ExactCashComparisonResult` identifies the comparison
operation/version, policy identity/version, context identity, engine version,
inclusive recorded and economic cutoffs, and settlement date. The result's
breaks are ordered by the complete account/currency key and then break kind.

An `ExactCashBreak` retains the applicable `ExactCashReductionResult` and
`CashObservation` as separate optional values. A mismatch therefore exposes the
projection's intermediate reduction identity, policy, full context,
source-event IDs and source-record IDs alongside—but never merged with—the
observation's provenance. A missing observation retains only its projection;
an unexpected observation retains only external evidence; an exact match emits
no break. Neither input is mutated or promoted to another authority role.

The comparison validates every input before returning a result. It rejects
duplicate projected keys, duplicate observations, an invalid account identity,
an inconsistent key/amount currency, any difference in a projection's complete
evaluation context, an observation at another economic or settlement cutoff,
incomplete comparison operation/policy identities, and checked subtraction
overflow. Public `ExactCashReductionResult` and `CashObservation` construction
derive their key currency from their `Money`, so an inconsistent currency is
normally unrepresentable before comparison; the boundary still checks that
invariant. Distinct valid keys are not compared across account or currency:
they become missing or unexpected breaks, with no implicit FX or aggregation.
All failures have stable `ExactCashComparisonError` categories and return no
partial result.

Comparison neither mutates the ledger nor makes the observation authoritative.
Swapping projected and observed ports changes meaning, so it claims no
commutativity, associativity, identity, distributivity, or inverse. Its only
arithmetic is exact scale-6 `observed - projected` through `Money::subtract`.

## Standalone exact-cash execution host

`luca-exact-cash` is the first bounded portable host for these two public
operations. It reads one request from standard input by default, or from the
single file named by `--input FILE`, and writes one result to standard output.
It performs no file discovery and has no database, network, environment-secret,
plugin, or runtime-code input. The host parses and validates the envelope, but
delegates exact addition and comparison subtraction to `reduce_exact_cash` and
`compare_exact_cash`; it does not implement a second financial calculator.

The request and result both use the closed
`luca.exact-cash-cli.v1` schema. The complete example is
`tests/fixtures/exact-cash-cli/valid-mismatch.json`. Every request contains
exactly these top-level members:

| Member | Contract |
| --- | --- |
| `schema_version` | Exactly `luca.exact-cash-cli.v1`. |
| `engine` | Explicit `id` and `version`. V1 supports engine ID `luca`; its version is copied into `ExactCashEvaluationContext` and every operation trace. |
| `operations` | One reduction and one comparison declaration. V1 accepts `reduce.cash.exact`/`1` with `exact-cash-sum`/`1`, and `compare.cash.exact`/`1` with `exact-cash-comparison`/`1`. |
| `evaluation_context` | Context ID, inclusive `recorded_through`, inclusive `economic_as_of`, and `settlement_as_of_date`. UTC timestamps use exactly `YYYY-MM-DDTHH:MM:SSZ`; dates use `YYYY-MM-DD`. |
| `partials` | Explicit account, currency, exact amount, source-event IDs, and source-record IDs for each reduction input. |
| `observations` | Explicit account, currency, exact amount, both observation cutoffs, and complete observation provenance. |

The reduction declaration also fixes `unit: money`, complete ordered
`partition_keys: [account, currency]`, `ordering: arbitrary`, and
`rounding: none`. The comparison declaration fixes output ordering by account,
currency, and break kind, `rounding: none`, and the existing
`observed_minus_expected` sign convention. These declarations are mandatory;
the host neither guesses them nor accepts alternative spellings. Every amount
is a JSON string in canonical scale-6 form. It has exactly six fractional
digits, no plus sign or leading integer zero, and no exponent; `0.000000` is the
only zero spelling. The bytes are passed directly to `Money::parse`, never
through binary floating point.

All partials share the declared operation, policy, engine, and evaluation
context. The host creates an `ExactCashReductionContract` and
`ExactCashPartial` through their public factories for every input, groups them
by the complete `(account, currency)` key, then calls `reduce_exact_cash` once
per group. Event identity is unique across a request; repeated event lineage is
rejected rather than counted twice. Source-record lineage is canonicalized by
the public reducer. The host separately creates each observation with
`Provenance::create` and `CashObservation::create`; observation provenance
source IDs are unique and sorted. The requested observation cutoffs are not
replaced by the shared context, so `compare_exact_cash` reports a mismatch
instead of silently normalizing incompatible context.

The result contains the explicit engine and evaluation context, the reduction
and comparison operation trace, counts for exact/missing/unexpected/mismatch
outcomes, ordered reductions, ordered exact `matches`, and ordered `breaks`.
Exact matches retain projection and observation evidence in separate members.
Each break similarly has separate nullable `projection_evidence` and
`observation_evidence`; projection event/source lineage is never combined with
external provenance. Missing observations retain only projection evidence,
unexpected observations retain only observation evidence, and mismatches use
`difference = observed - expected`. No job ID, path, clock time, process ID,
attempt, hostname, or other runtime-specific host field appears in the result.
Identical request bytes therefore produce identical result bytes.

V1 is deliberately bounded: input is at most 1 MiB, JSON nesting is at most 16
levels, a JSON container has at most 8192 entries, partial and observation
counts are each at most 4096, lineage arrays are at most 4096 entries, and a
decoded string is at most 65536 bytes. The parser rejects malformed UTF-8,
malformed JSON, trailing input, duplicate members at any level, unknown schema
members, noncanonical decimals, excessive sizes/counts/nesting, unsupported
schema/operation/policy versions, invalid identifiers/currencies/dates/
provenance, duplicate observation keys or event lineage, incompatible
contexts, and checked arithmetic overflow. A failure writes one stable category
to standard error, exits nonzero, and writes no partial result to standard
output.

This JSON is a host envelope, not the portable canonical serialization deferred
to O3. In particular, it defines no input or output hash. Its deterministic
member order is useful for repeatable execution and tests but is not advertised
as a general LUCA canonical JSON format. The executable links only the public
`luca::reconciliation` target, so installed-library and parent consumers keep
their existing interfaces.

### Dependency-free Python client

`tools/exact-cash/python/luca_exact_cash` is an importable standard-library
adapter for this host envelope. Importing it defines types and constants only:
it does not launch a process, discover an executable, read configuration or
secrets, or access a filesystem, database, or network service. The caller
supplies a JSON-compatible request and an explicit executable path containing a
directory component. The adapter passes that path as the sole member of an
argument vector with `shell=False`; it never resolves a bare command through
`PATH` and never interprets metacharacters.

For example, add `tools/exact-cash/python` to the application's Python module
search path and call the client with an explicit local installation:

```python
import json
from pathlib import Path

from luca_exact_cash import Limits, run_exact_cash

request = json.loads(Path("exact-cash-request.json").read_text(encoding="utf-8"))
result = run_exact_cash(
    request,
    "/opt/luca/bin/luca-exact-cash",
    limits=Limits(
        timeout_seconds=5.0,
        max_request_bytes=1024 * 1024,
        max_stdout_bytes=16 * 1024 * 1024,
        max_stderr_bytes=64 * 1024,
    ),
)
print(result["breaks"])
```

Request serialization is strict UTF-8 JSON, rejects non-JSON constants such as
`NaN`, and stops at the configured request-byte limit. The adapter concurrently
drains standard output and standard error into separate bounded buffers,
terminates the child on either output limit or the configured timeout, and
waits for the explicitly named process. It returns only after standard output
decodes as one JSON object (surrounding JSON whitespace is allowed), has exactly
the supported `luca.exact-cash-cli.v1` identity, and contains list-valued
`operation_trace`, `projections`, `matches`, and `breaks` collections. A second
JSON value, log text, unsupported identity, duplicate JSON member, or missing or
non-list result collection is rejected. The adapter deliberately does not
validate accounts, currencies, amounts, context compatibility, lineage,
policies, or financial results; all such validation and all reduction and
comparison arithmetic remain in the C++ host.

Every client failure derives from `ExactCashClientError` and exposes a stable
`code`. Separate typed failures cover invalid limits or requests, missing or
unlaunchable executables, timeout, bounded stdout/stderr overflow, signal
termination, ordinary nonzero exit, process communication, malformed or extra
stdout, unsupported result schema, and an invalid result envelope. A nonzero
host failure exposes only its numeric status and, when stderr begins with the
host's bounded stable diagnostic form, its short category. Exceptions never
retain or print request data, observation or lineage payloads, the process
environment, or captured tool output.

This directory is source-importable reference code, not a published package or
native extension. An application owns how it supplies the explicit request and
executable path; the adapter adds no storage, scheduling, permissions, runtime
plugin loading, or host metadata to the deterministic result.

## Replay and invalidation

The exact cash fixture and public reducer demonstrate equal values and lineage
for three supported reduction paths: full input, a verified prefix plus suffix,
and compatible partial reduction plus merge. This does **not** claim that the
other projection APIs inherit the reducer's laws or expose general incremental
replay. Checkpoint and serialization contracts remain separate from this API.

Incremental or partitioned execution is supported only when its operation
declaration says so and all compatibility conditions hold. Otherwise full
recomputation from immutable inputs is the baseline. In particular:

| Change | Prior-result rule | Required response |
| --- | --- | --- |
| New ordinary input after a verified reduction prefix | Reuse only for an operation that declares a compatible reduction and unchanged operation/policy/context versions. | Apply the suffix and verify the result equals full reduction. |
| Late correction, cancellation, or reversal knowledge | Do not append the raw lifecycle record directly to projection state and do not treat it as an inverse. | Resolve the affected economic identity again and recompute affected account/instrument/currency/settlement partitions and downstream results. |
| `recorded_through` or `economic_as_of` change | A result belongs to the old context. Advancing a cutoff is incremental only if the operation explicitly supports it and no earlier active input changed; moving backward is not append-only. | Select/resolve inputs for the new complete context, then recompute or use a later verified incremental contract. |
| `settlement_as_of_date` change | Position may be unchanged, but settled cash and open obligations from the old date are incompatible. | Re-evaluate settlement-dependent folds. In the equity fixture, advancing to `2026-06-04` clears the payable and makes trade cash eligible. |
| Engine, operation, or policy version change | Prior deterministic output is incompatible even when values happen to compare equal. | Recompute that operation and every downstream consumer using the new declared versions. |
| Partition-key or merge-policy change | Existing partials do not prove compatibility. | Reject their merge and recompute with the new complete keys/policy. |

The fixtures use `prior_result_reuse: rejected` for lifecycle, policy, and
context changes. That phrase specifies semantic invalidation only; it is not a
checkpoint schema or storage command.

## Lineage and explanation

A composed semantic result explains:

- source-record identifiers and resolved economic-event/record identifiers;
- every intermediate operation identity and version;
- each operation's policy identity and version;
- the shared evaluation-context identity and engine version; and
- separate projection and observation evidence for reconciliation breaks.

The corrected equity result therefore identifies both the original and
correction source records, the active corrected record, lifecycle resolution,
the downstream map/fold operations, policies, and context. A composed operation
must propagate this information from its explicit inputs. It may not recover
lineage through a hidden database or network lookup.

For `compare.cash.exact`, the returned comparison contract is the operation
trace and each retained projection is its immediately preceding reduction
trace. Observation provenance stays on the observation side of a break; it is
never added to the projection's event or source-record lineage.

Canonical bytes, input hashes, output hashes, and state/checkpoint hashes are
intentionally absent. O3 must define their canonical serialization before a
hash can be portable. Until then, equal fixture JSON or equal arithmetic is not
called a canonical LUCA hash.

Host-only data such as job IDs, queue names, worker addresses, attempt counts,
requesting principals, wall-clock start/end times, storage locations, and
authorization decisions must be recorded outside the deterministic result. A
hosted adapter can eventually call the same reviewed OSS implementation and
fixtures as the standalone process and dependency-free Python client. Neither
portable host duplicates financial arithmetic from the public C++ operations.

## Fixture and validator responsibilities

The fixture set contains four independently parseable documents:

- `valid-exact-cash-reduction.json` proves exact arithmetic, identity,
  associativity, commutativity on the bounded declared domain, full/incremental/
  partitioned equality, and complete event/source lineage;
- `valid-equity-lifecycle-fold.json` composes fixture normalization, O2
  resolution, position mapping/reduction, and current cash/settlement semantics;
  it includes the ordering counterexample and lifecycle/policy/context
  invalidation expectations;
- `valid-cash-reconciliation.json` fixes exact comparison arithmetic and keeps
  projection lineage distinct from observation evidence; its `800.000000 USD`
  versus `790.000000 USD` result is also executed by the focused C++ and both
  public-package consumer tests; and
- `invalid-compositions.json` fixes the incompatibility categories and the
  settlement-direction partition counterexample.

`tests/conformance/test_transformation_contract.py` checks JSON shape, stable
identifiers, all operation declarations, compatible edges, ordering and
partition metadata, exact `Decimal` assertions, lineage references, law
examples, invalidation coverage, and stable negative categories. Fixture-level
checks bind each demonstrated operation's port types, units/currencies,
ordering, partition keys and merge, and rounding declaration to the concrete
cash or equity data; internally compatible but false declarations are rejected.
For the single resolved-trade example the validator also binds the declared
position, pre-settlement cash, obligation key/direction/amount, and arithmetic
operands to the selected active record and evaluation context. Reconciliation
output lineage must exactly match the projected and observed inputs in their
distinct roles. This deliberately narrow checking does not select events,
resolve arbitrary lifecycle graphs, calculate general portfolio state, or
reconcile arbitrary records; those remain responsibilities of reviewed LUCA
implementations and their engine conformance tests.

## Explicit deferrals and unresolved policy choices

This increment intentionally leaves the following to their roadmap owners:

- canonical wire serialization, input/output hashes, watermarks, and checkpoint
  compatibility (O3);
- journal types, charts of accounts, journal mapping signatures, accounting
  policy versions, trade-date versus settlement-date posting, lots, cost basis,
  P&L, and accounting rounding (O4);
- public transformation interfaces beyond the bounded exact-cash reduction and
  exact cash comparison, including general mapping, ordered-fold, tolerant
  comparison, and policy extension contracts;
- native Python bindings, hosted adapters, package publication, and pinned
  platform integration (later portable-execution increments); this increment's
  source-importable Python adapter only supervises the bounded standalone host;
- dynamic loading, a general plugin ABI, expression languages, arbitrary runtime
  code execution, and acceptance of externally calculated state;
- FX conversion/netting policy, fees, commissions, taxes, settlement calendars,
  partial reversals, cross-account corrections, and legal obligation netting;
  and
- production schemas, persistence, scheduling, permissions, network access,
  deployments, and platform host metadata.

These are not silently assigned default financial meaning by the fixtures. In
particular, no journal policy is encoded as fact, no FX rate is inferred, no
payable is netted with a receivable, and no custom or externally hosted result
becomes authoritative merely because it conforms to this design vocabulary.
