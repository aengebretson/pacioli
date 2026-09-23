# Immutable event lifecycle contract

Status: executable design contract for O2. This document and the JSON fixtures
define the behavior that a later C++ implementation must expose. They do not
describe an implemented public API or a durable serialization format.

## Baseline and boundary

The current core already provides the following contracts:

| Concern | Current contract | Lifecycle gap |
| --- | --- | --- |
| Canonical event | `EventHeader` identifies an immutable cash movement or equity trade by `EventId`, account, economic `effective_at`, and provenance. | There is no lifecycle action, recorded time, stable economic identity across versions, or causal reference. |
| Evidence | `SourceRecord` identifies immutable evidence. `Provenance` references one or more source records and a named/versioned normalization. | A lifecycle successor must retain its own evidence and must not overwrite its predecessor's provenance. |
| Ledger | `Ledger` rejects duplicate event IDs and assigns a local acceptance sequence. Economic replay orders by `(effective_at, sequence)`; append order is otherwise retained. | The ledger does not validate causal edges or select knowledge by recorded time. |
| Position | Economically selected equity trades add signed quantity on trade date. | It cannot yet select the active head of a corrected or cancelled chain. |
| Settled cash | Cash movements apply at economic time. Trade cash applies only when the supplied settlement date is eligible in the explicit projection context. | Lifecycle knowledge must be resolved before the same cash rule is applied. |
| Settlement | Economically selected trades create positive payable or receivable magnitudes until the supplied settlement date is reached. | Lifecycle knowledge must be resolved before the same obligation rule is applied. |

The first lifecycle increment extends these contracts; it does not reinterpret
existing accepted values. External observations and reconciliation breaks remain
non-authoritative evidence and cannot originate, correct, cancel, or reverse an
economic event.

## Identities and immutable records

A future lifecycle-aware ledger accepts immutable **ledger records**. Every
record has these concepts, named independently of any eventual C++ spelling:

- `record_id` identifies exactly one immutable accepted canonical record. It is
  unique for the ledger's identity scope and is never reused.
- `economic_event_id` identifies one economic intent across an origin and its
  correction/cancellation chain. Corrections retain it. Reversals use a new one.
- `acceptance_sequence` is a unique, increasing, ledger-local integer assigned
  when the record is accepted. It is an ordering input, not source or market
  order.
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
  event type, instrument, or currency. A wrong immutable relationship is
  cancelled and re-originated under a new economic identity.

`cancel`
: Carries no payload and retains the target's `economic_event_id`. It identifies
  the immediately preceding record through `supersedes_record_id` and closes
  the chain. Once known, that economic identity contributes no state at any
  economic cutoff. This is LUCA's semantic cancellation of erroneous economic
  evidence, not a mutable delete and not a claim about an exchange protocol's
  cancellation message.

`reverse`
: Carries a full offsetting payload under a new `economic_event_id` and points
  to the payload-bearing target with `reverses_record_id`. The target remains
  active; the reversal contributes at its own `effective_at`. For this first
  contract a reversal is complete: cash amount or trade quantity is the exact
  opposite, and account, type, instrument, price, and currency match. A reversal
  may have a later supplied settlement date. Partial reversals are deferred.

**Supersession** is the relationship expressed by `supersedes_record_id`, not a
fifth financial action. A correction supersedes a payload with a replacement;
a cancellation supersedes it with a terminal no-payload record. Original and
superseded records remain addressable evidence.

The causal graph is an unbranched forest. A target must exist, must not refer to
itself, must be earlier in knowledge order, and may have at most one direct
lifecycle successor across correction, cancellation, or reversal. Cycles are
invalid. The referenced record must be the open head appropriate to the action;
a cancelled record is terminal. This intentionally closes a record after a
reversal so a later change cannot silently make the offset incompatible.

## Validation and diagnostics

Lifecycle consistency is checked before acceptance and must fail without
mutating the ledger. The portable contract fixes these diagnostic categories;
an implementation may attach more detail, record IDs, and field paths:

| Category | Meaning |
| --- | --- |
| `causal_reference_missing` | A causal ID does not identify an accepted record. |
| `causal_self_reference` | A record targets itself. |
| `causal_cycle` | Causal edges form a cycle. |
| `causal_reference_unavailable` | The target is not earlier in recorded/acceptance order. |
| `incompatible_account` | Target and action cross account boundaries. |
| `incompatible_event_relationship` | Economic identity, event type, natural key, or reversal terms are incompatible. |
| `conflicting_lifecycle_successor` | A target already has a correction, cancellation, or reversal successor. |

Ordinary shape errors, duplicate record/economic-origin identities, invalid
times, missing provenance, and duplicate ordering inputs are also rejected. The
fixture validator exercises the stable causal categories above without
implementing portfolio arithmetic.

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
2. Resolve selected correction/cancellation chains in causal order. A selected
   active chain contributes exactly its active full payload. A selected
   cancelled chain contributes none. A reversal is an active independent chain
   whose causal link is retained.
3. Select active payloads with `effective_at <= economic_as_of` and replay them
   by `(effective_at, acceptance_sequence)`. The sequence of the active payload
   record is the deterministic tie-breaker.
4. Feed that same ordered active set and the same explicit context to every
   affected projection. Position uses economic time. Settled cash and open
   obligations additionally use `settlement_as_of_date` exactly as today.

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

## Deferred implementation choices

This contract does not choose public class names, persistence layout, canonical
wire encoding, hashes, checkpoint invalidation metadata, concurrent acceptance,
or cross-ledger/global sequence allocation. Serialization and checkpoints remain
O3 work. Incremental processing may be added only when it proves equivalent to
full replay and invalidates state affected by late lifecycle records.

Partial reversals, multiple independent reversals, changes of account or natural
key within a correction, and lifecycle action after a closed reversal are not
accepted by this first contract. A later financial-policy decision may add them
with new conformance cases; implementations must not infer them from these
fixtures.
