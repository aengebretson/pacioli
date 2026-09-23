# Immutable event lifecycle contract

Status: executable design contract plus public C++ lifecycle resolution and
portfolio projection adoption. `luca/lifecycle.hpp` implements immutable
in-memory acceptance and two-cutoff active-event resolution;
`luca/portfolio/lifecycle_projection.hpp` feeds one resolved active set to the
existing position, settled-cash, and open-settlement projections. Durable
serialization remains a later increment.

## Baseline and boundary

The current core already provides the following contracts:

| Concern | Existing contract | Implemented lifecycle increments |
| --- | --- | --- |
| Canonical event | `EventHeader` identifies an immutable cash movement or equity trade by `EventId`, account, economic `effective_at`, and provenance. | `LifecycleRecord` adds action, stable `EconomicEventId`, recorded time, acceptance sequence, and causal reference while retaining the complete event payload. |
| Evidence | `SourceRecord` identifies immutable evidence. `Provenance` references one or more source records and a named/versioned normalization. | Each lifecycle record retains its own provenance; accepting a successor does not edit predecessor evidence. |
| Ledger | `Ledger` rejects duplicate event IDs and assigns a local acceptance sequence. Economic replay orders by `(effective_at, sequence)`; append order is otherwise retained. | Separate `LifecycleLedger` acceptance validates causal edges and resolves knowledge by recorded time without changing `Ledger`. |
| Position | Economically selected equity trades add signed quantity on trade date. | `project_lifecycle` derives positions from the resolution's active set at the explicit economic cutoff. |
| Settled cash | Cash movements apply at economic time. Trade cash applies only when the supplied settlement date is eligible in the explicit projection context. | `project_lifecycle` derives settled cash from that same active set while settlement evaluation stays an independent input. |
| Settlement | Economically selected trades create positive payable or receivable magnitudes until the supplied settlement date is reached. | `project_lifecycle` derives open obligations from that same active set and explicit settlement date; no settlement clock is inferred. |

The first lifecycle increment extends these contracts; it does not reinterpret
existing accepted values. External observations and reconciliation breaks remain
non-authoritative evidence and cannot originate, correct, cancel, or reverse an
economic event.

## Identities and immutable records

`LifecycleLedger` accepts immutable **ledger records**. Every record has these
concepts:

- `record_id` identifies exactly one immutable accepted canonical record. It is
  spelled `EventId` in the public API, is unique for the ledger's identity
  scope, and is never reused. For payload-bearing records it is the ID already
  carried by `EventHeader`.
- `economic_event_id` identifies one economic intent across an origin and its
  correction/cancellation chain. It is a distinct strong `EconomicEventId`.
  Corrections retain it. Reversals use a new one.
- `acceptance_sequence` is a unique, increasing, ledger-local integer assigned
  as `LifecycleSequence` when the record is accepted. It is an ordering input,
  not source or market order.
- `recorded_at` is LUCA's knowledge time for the accepted canonical record. It
  is distinct from a source record's observation or source-event time.
- `effective_at` is the economic time of a payload. A cancellation has no
  payload and therefore no economic timestamp of its own.
- `provenance` belongs to that immutable record. An active chain's lineage is
  the ordered provenance of every record in the chain; accepting a successor
  never edits or replaces predecessor evidence.

The fixtures spell out source records so provenance references can be checked.
Their JSON is a portable conformance vocabulary, not O3 canonical
serialization.

## Public C++ API

`LifecycleRecordDraft::originate`, `correct`, `cancel`, and `reverse` make each
action's payload and causal-reference shape explicit. A draft has no acceptance
sequence. `LifecycleLedger::accept` validates one draft and
`LifecycleLedger::accept_batch` validates a span transactionally, assigning
contiguous ledger-local sequences only after the whole operation succeeds. The
batch form is necessary to diagnose forward references and causal cycles; any
validation failure leaves accepted records and the next sequence unchanged.

Accepted records are available in acceptance order through `records()` and by
record identity through `find()`. `resolve(recorded_through, economic_as_of)`
returns every knowledge-selected chain, including terminal cancelled chains,
plus its ordered `active_events()`. An active result exposes its selected record,
complete same-economic-identity lineage, immutable provenance on every lineage
record, and the reversed target when applicable. Returned references have the
same in-memory invalidation constraint as `Ledger` views: later acceptance can
reallocate record storage, so callers request a fresh resolution after mutation.

`project_lifecycle(resolution, context)` is the narrow portfolio adapter. Its
`LifecycleProjectionContext` names the economic cutoff separately from the
settlement evaluation date. The adapter consumes only
`resolution.active_events()`; it does not select lifecycle heads, validate
causal references, or reinterpret the recorded-time cutoff. It materializes the
ordered active payloads once through the existing `Ledger` API and invokes the
unchanged position, cash, and settlement projection functions on that identical
set. `LifecycleProjectionResult` retains each existing projection's
`std::expected` and error type, so one overflow does not hide the independently
evaluated results of the other views.

Callers should pass the same economic cutoff to `LifecycleLedger::resolve` and
`project_lifecycle`. The adapter reapplies that cutoff through the existing
projection APIs, but a resolution made with an earlier economic cutoff has
already omitted later payloads and cannot be widened. The supplied resolution
remains the inspection surface for chains, original records, provenance,
acceptance sequences, and reversal targets; projection does not copy or mutate
that lineage.

`LifecycleError` reports the stable category, offending record ID, optional
causal target, and a diagnostic message. `category_name` exposes the exact
portable category spelling. Shape, duplicate-identity, deterministic-ordering,
and sequence-exhaustion errors are also explicit, but are not added to the
stable causal-category set below.

## Lifecycle actions and supersession

`originate`
: Starts a new `economic_event_id` with a full cash-movement or equity-trade
  payload and no causal reference.

`correct`
: Carries a complete replacement payload, retains the target's
  `economic_event_id`, and identifies the immediately preceding record through
  `supersedes_record_id`. Once the correction is known, the replacement is the
  only active payload for that economic identity. It may change quantity,
  amount, price, effective time, or supplied settlement date, but not account,
  event type, instrument, or currency. Its target must be an open `originate`
  or `correct` record; a reversal is not correctable. A wrong immutable
  relationship is cancelled and re-originated under a new economic identity.

`cancel`
: Carries no payload and retains the target's `economic_event_id`. It identifies
  the immediately preceding record through `supersedes_record_id` and closes
  the chain. Once known, that economic identity contributes no state at any
  economic cutoff. This is LUCA's semantic cancellation of erroneous economic
  evidence, not a mutable delete and not a claim about an exchange protocol's
  cancellation message. Its target must be an open `originate` or `correct`
  record; neither cancellations nor reversals can themselves be cancelled.

`reverse`
: Carries a full offsetting payload under a new `economic_event_id` and points
  to the payload-bearing target with `reverses_record_id`. The target remains
  active; the reversal contributes at its own `effective_at`. For this first
  contract a reversal is complete: cash amount or trade quantity is the exact
  opposite, and account, type, instrument, numerically equal price, and currency
  match. A reversal may have a later supplied settlement date. Accepting it
  closes its target, and the new reversal root is itself terminal: no correction,
  cancellation, or further reversal may target either record. Partial reversals
  and changes to an accepted reversal are deferred.

**Supersession** is the relationship expressed by `supersedes_record_id`, not a
fifth financial action. A correction supersedes a payload with a replacement;
a cancellation supersedes it with a terminal no-payload record. Original and
superseded records remain addressable evidence.

The causal graph is an unbranched forest. A target must exist, must not refer to
itself, must be earlier in knowledge order, and may have at most one direct
lifecycle successor across correction, cancellation, or reversal. Cycles are
invalid. The referenced record must be the open head appropriate to the action;
a cancelled record and a reversal record are terminal. This intentionally fixes
both sides of an accepted reversal relationship so a later lifecycle action
cannot silently make its exact offset incompatible. A new correction to the
underlying business fact therefore requires a separately evidenced cancellation
and re-origination policy in a future contract; this contract does not infer one.

## Validation and diagnostics

Lifecycle consistency is checked before acceptance and fails without mutating
the ledger. The portable contract fixes these diagnostic categories; the public
error also attaches the offending record, optional target, and more detail:

| Category | Meaning |
| --- | --- |
| `causal_reference_missing` | A causal ID does not identify an accepted record. |
| `causal_self_reference` | A record targets itself. |
| `causal_cycle` | Causal edges form a cycle. |
| `causal_reference_unavailable` | The target is not earlier in recorded/acceptance order. |
| `incompatible_account` | Target and action cross account boundaries. |
| `incompatible_event_relationship` | Economic identity, event type, natural key, reversal terms, or terminal-action policy are incompatible. |
| `conflicting_lifecycle_successor` | A target already has a correction, cancellation, or reversal successor. |

Ordinary shape errors, duplicate record/economic-origin identities, decreasing
recorded times, missing provenance, and exhausted ordering inputs are also
rejected. The fixture validator exercises the stable causal categories above
without implementing portfolio arithmetic.

## Supported evaluation model

Every projection evaluation supplies all three values:

```text
recorded_through          inclusive knowledge cutoff
economic_as_of            inclusive economic cutoff
settlement_as_of_date     independent date-granular settlement evaluation
```

Evaluation is deterministic:

1. Select records with `recorded_at <= recorded_through`. Accepted timestamps
   are nondecreasing with sequence; equal timestamps are ordered by
   `acceptance_sequence`.
2. Group every selected record by `economic_event_id`, follow each complete
   causal path from its `originate` or `reverse` root, and resolve the
   knowledge-time head. Every selected economic identity appears exactly once
   as either an active chain or a cancelled chain; a fixture cannot omit a known
   successor or identity. An active chain contributes exactly its head's full
   payload. A cancelled chain contributes none. A reversal is an active,
   terminal independent chain whose causal link is retained.
3. Select active payloads with `effective_at <= economic_as_of` and replay them
   by `(effective_at, acceptance_sequence)`. The sequence of the active payload
   record is the deterministic tie-breaker.
4. Feed that same ordered active set and the same explicit context to every
   affected projection. Position uses economic time. Settled cash and open
   obligations additionally use `settlement_as_of_date` exactly as today.

The lifecycle resolver accepts the first two cutoffs and performs steps 1–3.
The portfolio adapter accepts the already resolved result plus the explicit
economic and settlement inputs, then performs step 4 through the existing
projection APIs. `LifecycleLedger::resolve` deliberately does not accept or
interpret `settlement_as_of_date`.

Consequently, a late-recorded correction can change an earlier economic result
in a newer knowledge view while the old `recorded_through` view stays
reproducible. A reversal preserves the target's earlier effect and offsets it
only when the reversal is economically effective. Full replay of identical
records and context must produce byte-for-byte-equivalent normalized results in
all supported execution paths.

This is a deliberately limited two-cutoff evaluation contract, not a general
bitemporal database promise. It does not support recorded-time ranges, querying
inside an equal-timestamp acceptance batch, arbitrary valid-time intervals,
retroactive source-system belief, market-calendar inference, settlement
timestamps, or automatic transaction-time joins. `recorded_at` describes when
LUCA accepted canonical knowledge, not when a source first knew a fact.

## Fixtures and arithmetic

The portable fixtures under `tests/conformance/event-lifecycle/` contain source
records, ledger records, complete evaluation contexts, active and inactive
chains, source lineage, projection expectations, and human-checkable arithmetic.
The focused C++ lifecycle-projection test executes the cash and equity fixture
expectations across their recorded-time, economic-time, and settlement-date
boundaries while retaining lineage inspection through the supplied resolution.

The late cash fixture proves `1,000 -> 1,200 -> 0`: the correction replaces the
original `+1,000` with `+1,200` once known, and the later cancellation removes
that chain from projection without erasing either evidence record.

The equity fixture starts with `100,000` USD. Before correction, `100 × 50 =
5,000`; after correction, `80 × 55 = 4,400`. Trade-date state is 80 shares,
100,000 settled cash, and a 4,400 payable. Trade settlement produces `100,000 -
4,400 = 95,600`. The late-known reversal adds `-80` shares and a 4,400
receivable, then reversal settlement restores `95,600 + 4,400 = 100,000`.

Journals are marked `deferred` because O4 does not yet exist. When journal
projection is implemented, it must consume the identical resolved active set and
context; the fixture contract can then add explicit journal expectations without
changing lifecycle meaning.

## Deferred work

This increment does not choose a persistence layout, canonical wire encoding,
hashes, checkpoint invalidation metadata, concurrent acceptance, or
cross-ledger/global sequence allocation. Serialization and checkpoints remain
O3 work. Incremental processing may be added only when it proves equivalent to
full replay and invalidates state affected by late lifecycle records. Journal
projection remains deferred; when introduced, it must consume the same resolved
active set and explicit evaluation context rather than independently resolving
lifecycle knowledge.

Partial reversals, multiple independent reversals, changes of account or natural
key within a correction, and any lifecycle action targeting an accepted
reversal are not accepted by this first contract. A later financial-policy
decision may add them with new conformance cases; implementations must not infer
them from these fixtures.
