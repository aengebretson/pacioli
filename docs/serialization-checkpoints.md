# Canonical serialization and replay-checkpoint contract

Status: executable O3 design contract with production exact-scalar and lifecycle
C++ encoding slices.
The fixtures and dependency-free validator under
`tests/conformance/serialization-checkpoints/` fix the first portable byte,
digest, manifest, and checkpoint-resume semantics. This contract is grounded in
the immutable lifecycle resolution and the position, settled-cash, and open-
settlement projections already implemented. It does not add a persistence
format.

## Boundary and purpose

The contract permits an authorized process to receive canonical lifecycle input,
a verified portfolio-state checkpoint, and an ordinary append-only suffix and to
decide deterministically whether reuse is safe. A standalone process receiving
the same values can reproduce the canonical bytes, verify every digest, and
compare full replay with checkpoint-plus-suffix results without knowing C++
object layout.

This v1 checkpoint contains all three current portfolio views as one result:

- sparse positions by account and instrument;
- sparse settled cash by account and currency; and
- positive open settlement obligations by account, settlement date, currency,
  and direction.

The canonical values are calculation exchange values. They are not deferred
backtesting dataset snapshots, database rows, ABI dumps, or an authorization
envelope. Source payload storage and authorization to obtain inputs stay outside
the deterministic financial result.

## LCB1 canonical bytes

`luca.canonical-bytes.v1`, abbreviated **LCB1**, is the byte representation used
by every vector in this contract. It is a small, deterministic value encoding,
not JSON serialization. JSON is only the human-portable fixture container.

Every top-level value begins with the four ASCII octets `4c 43 42 31` (`LCB1`),
followed by exactly one node. Integers in lengths and payloads use network byte
order. No trailing bytes are allowed.

| Tag | Value | Payload |
| --- | --- | --- |
| `00` | null | none |
| `01` | false | none |
| `02` | true | none |
| `03` | signed integer | eight-octet two's-complement signed integer |
| `04` | text | unsigned 32-bit byte length, then NFC UTF-8 bytes |
| `05` | array | unsigned 64-bit item count, then canonical child nodes in declared order |
| `06` | map | unsigned 32-bit member count, then members in ascending raw UTF-8 key-byte order |

A text length, map member count, or map key length is unsigned 32-bit. A map
member is its key-byte length, its NFC UTF-8 key bytes
without a text tag, and one canonical value node. Keys must be unique. The v1
format rejects invalid UTF-8, non-NFC text, binary floating point, integers
outside signed 64-bit range, an array item count above `2^64 - 1`, another
length/count above `2^32 - 1`, unknown tags, duplicate members, non-canonical
map order, truncated input, and trailing input. The distinct unsigned 64-bit
array count is required because the public ledger may accept every lifecycle
sequence from 1 through `18446744073709551615`; LCB1 can therefore represent
the corresponding complete contiguous record array without narrowing the public
domain. The fixture decoder checks decode/encode round trips, not only digest
equality.

All schema maps contain a `schema_version` text member. The field therefore
participates in canonical bytes and digests. An implementation must reject an
unknown version; it must not interpret it as the nearest known shape. `LCB1` in
the byte header versions the value grammar, while each `schema_version` versions
the financial value. Changing either changes canonical bytes.

### Scalar normalization

The domain-to-LCB mapping is independent of compiler, platform, locale, JSON
parser, and memory representation:

| Domain value | Canonical value |
| --- | --- |
| Identifier | Non-empty NFC text without NUL. Identifiers remain opaque and case-sensitive; no trimming or case folding occurs. A public value that is not NFC is rejected by the v1 serializer rather than silently changing identity. |
| Variant | A closed lower-case `variant` or `action` text tag plus exactly the fields of that alternative. Unknown tags and fields are rejected. |
| Timestamp | UTC ISO 8601 text `YYYY-MM-DDThh:mm:ss.nnnnnnnnnZ`, always nine fractional digits. A `Timestamp` time point is rendered in UTC; equivalent offsets cannot produce different bytes. Fixture years are `0001` through `9999`. |
| Settlement date | Valid proleptic-Gregorian `YYYY-MM-DD` text, with no time or timezone. |
| Fixed point | An object containing its version, a canonical signed base-10 `scaled_value` string, and canonical non-negative `scale` string. `0` is the only zero spelling; leading plus, leading zero, decimal point, exponent, whitespace, and `-0` are forbidden. The parsed scaled value must fit signed 64-bit. |
| Currency | Exactly three uppercase ASCII letters. Money contains its currency; price remains currency-neutral and an equity trade carries `quote_currency`. |
| Sequence/watermark integer | Canonical positive base-10 text parsed as unsigned 64-bit (`1` through `18446744073709551615`). Text avoids loss in fixture consumers whose JSON numbers cannot represent the complete public `LifecycleSequence` domain. The text is an LCB string node, so it is not constrained by LCB1's signed primitive-integer tag. |
| Optional value | The member is always present. Absence is tag `00` null; presence is the canonical child value. Omitting the member is not equivalent. |
| Ordered collection | LCB array in the financial order defined below. An implementation may use an unordered container internally but must emit this order. |

JSON numbers appear only in the primitive grammar vector. Authoritative fixed-
point and sequence values use canonical strings in the schema before LCB
encoding. Binary floating point is never accepted for money, quantity, price,
rate, sequence, or watermark values.

### Typed C++ encoding API

`<luca/serialization/canonical.hpp>` provides the ledger production encoding
slices, and `<luca/portfolio/serialization.hpp>` adds the portfolio-state
slice. `luca::serialization::canonical_bytes` and `canonical_digest` are a
closed, typed overload set for `Money`, `Quantity`, `Price`, `Provenance`,
`EventHeader`, `CashMovement`, `EquityTrade`, `EconomicEvent`,
`LifecycleRecord`, `LifecycleLedger`, and `PortfolioState`. Bytes are returned
as an owned `CanonicalBytes` (`std::vector<std::byte>`), and the digest is
returned as 64 lower-case hexadecimal characters. The API is header-only and
is available to installed-package and `add_subdirectory` consumers through the
existing Luca targets; it has no third-party dependency.

Each overload emits the closed v1 map defined here. Money owns its currency,
scale `6`, scaled value, and `luca.money.v1` schema identity. Quantity and price
own scale `8`, their scaled value, and their distinct `luca.quantity.v1` or
`luca.price.v1` identity. The encoder formats signed 64-bit values directly as
canonical decimal text and hashes the complete LCB1 sequence. It does not expose
a generic value tree or accept caller-selected schema names, scale, or version.
The event overloads emit explicit closed variant tags and nested scalar maps.
The record overload retains the accepted action, causal reference, unsigned
sequence text, redundant header identity and optional event exactly as defined
below. `LifecycleLedger` is the complete-sequence boundary: lifecycle
acceptance has already established a contiguous unsigned 64-bit order beginning
at one, and its overload hashes one `luca.lifecycle-record-sequence.v1` value
rather than concatenating record encodings or hashes. Timestamps are rendered
in UTC with nanosecond precision and settlement dates retain date granularity.

## Covered public values

The following inventory is the complete v1 calculation surface. Field names
below are canonical schema members, not C++ member offsets.

### Provenance — `luca.provenance.v1`

`source_record_ids` is a non-empty, duplicate-free ordered array;
`transformation_name` and `transformation_version` are non-empty text; and
`transformation_metadata` is either null or NFC text (including empty text) of at most 1024
UTF-8 bytes. Source identifiers retain the order supplied by normalization, so
reordering them changes the value and digest. The public `SourceRecord` payload
is not needed to replay an already authorized canonical event and is not
embedded. Evidence retrieval remains separate; its referenced IDs remain in
lineage.

### Event header and economic-event variants

`luca.event-header.v1` contains `record_id`, `account`, `effective_at`, and
`provenance`. `luca.economic-event.v1` contains the event `header`, a `variant`,
and exactly one payload:

| Variant | Payload fields |
| --- | --- |
| `cash_movement` | `amount` as `luca.money.v1`, scale `6`; signed amount |
| `equity_trade` | `instrument`; non-zero `quantity` as `luca.quantity.v1`, scale `8`; `price` as `luca.price.v1`, scale `8`; `quote_currency`; `settlement_date` |

The variant tag is explicit; variant index, class layout, padding, native enum
size, and RTTI never enter the encoding.

### Immutable lifecycle record — `luca.lifecycle-record.v1`

Every record contains, in its canonical map, `record_id`,
`economic_event_id`, `account`, `action`, `recorded_at`, positive
`acceptance_sequence`, `causal_record_id`, `provenance`, and `event`.

- `originate` has a null causal ID and a complete event.
- `correct` has the superseded record ID and a complete replacement event.
- `cancel` has the superseded record ID and a null event.
- `reverse` has the reversed record ID and a complete offset event under its
  distinct economic identity.

For a payload-bearing record, record ID, account, and provenance must equal its
event header fields. This deliberate redundancy makes a malformed exchange value
rejectable rather than ambiguous. Records are serialized in contiguous
acceptance-sequence order beginning at 1. `recorded_at` cannot decrease. Causal
targets must already occur in that order. The current lifecycle relationship
rules continue to govern correction, cancellation, and reversal; serialization
does not loosen them.

A canonical input is one `luca.lifecycle-record-sequence.v1` map containing the
ordered `records` array. The array's unsigned 64-bit count and the record
sequence's unsigned 64-bit acceptance values cover the same complete domain, so
a record at or above sequence `4294967296` does not encounter a narrower
collection-count limit. The checkpoint's canonical input digest hashes this
whole value, not the concatenation of individual record hashes.

### Resolved economic events and lineage

A resolved event is exchanged without a second copy of its economic payload:
`lineage.active_record_ids` identifies selected payload-bearing lifecycle
records in replay order, and `lineage.lifecycle_record_ids` identifies the
complete accepted prefix in acceptance order. Looking up an active ID in that
prefix yields its exact canonical event and record provenance. Its causal ID
identifies the superseded or reversed record when present. This covers the public
`ResolvedLifecycleEvent` values—selected record, complete record lineage, and
reversal target—without creating an independently diverging event copy.

Active replay order is `(effective_at, acceptance_sequence)`, both ascending.
Complete lifecycle lineage stays in acceptance order. `source_record_ids` is the
ordered first occurrence of every provenance source ID while walking lifecycle
records and each record's provenance array. Reordering any of these ordered
arrays changes canonical bytes and is rejected where it violates the declared
order.

The validator checks the same structural lifecycle invariants as public
acceptance: an unbranched causal target, same account for related records,
retained economic identity for correction/cancellation, a distinct identity
for reversal, compatible event type and natural key, and exact reversal terms.
For lineage binding it selects records through `recorded_through`, takes the
unique head of every economic identity, removes cancellation heads and payloads
after `economic_as_of`, then orders the remaining heads by the replay key. The
declared `active_record_ids` must equal that derived set exactly; it cannot list
both a predecessor and correction, omit the true head, or substitute a head
from a different identity. This is lifecycle selection and validation, not a
second implementation of portfolio arithmetic.

### Portfolio state — `luca.portfolio-state.v1`

The state has exactly `positions`, `settled_cash`, and
`open_settlement_obligations` arrays:

| Value | Fields and order |
| --- | --- |
| `luca.position-balance.v1` | `account`, `instrument`, non-zero scale-8 `quantity`; unique and sorted by `(account UTF-8 bytes, instrument UTF-8 bytes)` |
| `luca.cash-balance.v1` | `account`, non-zero scale-6 money `amount`; unique and sorted by `(account UTF-8 bytes, currency)` |
| `luca.settlement-obligation.v1` | `account`, `settlement_date`, `direction`, positive scale-6 money `amount`; unique and sorted by `(account UTF-8 bytes, date, currency, direction)` where `receivable` precedes `payable` |

Sparse projection rules remain authoritative: zero position and cash balances
are omitted. Receivables and payables remain separate and are not netted.

The C++ `PortfolioState` exchange value owns vectors of the existing
`Position`, `CashBalance`, and `SettlementObligation` types. Its typed encoder
validates the sparse invariants and scalar representability, rejects duplicate
keys, and canonicalizes caller-supplied collection order without mutating the
value. Ordering compares identifier UTF-8 octets as unsigned bytes, so it is
independent of platform `char` signedness. The encoder fixes all four v1 schema
identities; callers cannot select or override a schema name or version.

### Evaluation context — `luca.evaluation-context.v1`

The context includes all three existing lifecycle projection inputs:
`recorded_through`, `economic_as_of`, and `settlement_as_of_date`. It also
contains sorted, duplicate-free arrays for `reference_data_inputs`,
`price_inputs`, `calendar_inputs`, `rounding_inputs`, and `fx_inputs`. Every
applicable external calculation input is identified by non-empty `id`, `version`,
and lowercase SHA-256 `digest`. An empty array explicitly means that kind of
input was not used; it does not authorize a hidden lookup. The equity fixture
declares the current half-even multiplication rule as a versioned rounding
input. Event-supplied prices and settlement dates do not create hidden price or
calendar dependencies.

## Digest rules

The only digest algorithm in v1 is SHA-256. The digest is the 32 bytes returned
by SHA-256 over the complete LCB1 top-level bytes, with no newline, prefix,
salting, chunk framing, or hex text in the hashed input. Fixtures and manifests
render those bytes as exactly 64 lower-case hexadecimal characters and canonical
bytes as lower-case hexadecimal octets.

The fixture vectors pin exact bytes and digests for primitive values, money,
provenance, lifecycle input sequences, states, manifests, and resume requests.
They regenerate every byte sequence twice and perform decode/encode round trips.
Changes to event payload, provenance, ordering, context, policy, partition,
engine, projection, or schema version therefore change the input, state, or
manifest digest that owns that field. A consumer verifies the claimed input and
state digest before considering compatibility.

## Checkpoint manifest

`luca.checkpoint-manifest.v1` contains exactly:

| Member | Meaning |
| --- | --- |
| `schema_version` | Manifest schema identity. |
| `serialization_version` | `luca.canonical-bytes.v1`. |
| `digest_algorithm` | `sha-256`. |
| `projection` | Stable projection identity and version; the fixture uses the combined portfolio-state projection. |
| `engine_version` | Financial engine version that produced the result. |
| `policy` | Financial policy identity and version. |
| `partition` | Partition-definition identity, version, and non-empty sorted partition keys. v1 supports `account-set` version `1`; every account in prefix records and checkpoint state must be one of its keys. |
| `event_prefix` | Inclusive acceptance-sequence prefix: kind, first and last sequence, count, last record ID, record schema version, and canonical input digest. v1 begins at sequence 1. |
| `evaluation_context` | Complete context and explicit versioned context inputs described above. |
| `canonical_state_digest` | SHA-256 of the canonical `luca.portfolio-state.v1` value. |
| `resolved_event_watermark` | Last selected active event's effective time, acceptance sequence, and record ID in economic replay order. |
| `lineage` | Complete prefix record IDs, active record IDs in replay order, and ordered source-record references. |

The canonical manifest itself can be hashed and is identified by
`checkpoint_manifest_digest` in `luca.checkpoint-resume.v1`. That request repeats
the compatibility-critical projection, engine, policy, partition, context,
prefix, and state digest. Repetition is intentional: each repeated value must
exactly match the verified manifest, so routing or cache metadata cannot silently
select a different calculation.

Job IDs, attempt IDs, worker IDs, execution or persistence timestamps, host and
object-store paths, credentials, authorization decisions, and transport metadata
are forbidden as unknown manifest fields. A storage or execution layer may keep
them in a sidecar that is neither part of the canonical financial result nor its
digest.

The C++ portfolio package exposes this contract as closed values rather than a
generic map or serialization runtime. `CheckpointIdentity`, `CheckpointInput`,
`AccountSetPartition`, `CheckpointEventPrefix`, `CheckpointEvaluationContext`,
`ResolvedEventWatermark`, `CheckpointLineage`, and `CheckpointManifest` are
created through validating factories. `Sha256Digest` owns the lowercase digest
form. Schema, serialization, digest-algorithm, account-set, prefix-kind, and
record-schema identities are fixed by the types and cannot be supplied by a
caller.

Factories copy caller declarations only after validation, so a failed operation
does not consume or reorder caller-owned vectors. Account keys and each explicit
context-input collection are copied into unsigned UTF-8 byte order; duplicate
keys or duplicate `(id, version)` inputs are rejected. Lifecycle, active-event,
and source-record lineage are retained exactly in their declared contract order.
Manifest construction additionally requires lineage to span the declared prefix
and requires the watermark sequence and record to identify the final
replay-ordered active lineage entry.

`luca::serialization::canonical_bytes(const CheckpointManifest&)` emits the
fixed LCB1 representation, and `canonical_digest` hashes those complete bytes
with SHA-256. These APIs only exchange and identify a manifest. They do not make
a checkpoint-resume decision, load state, apply an event suffix, decode bytes,
or introduce persistence, authorization, compression, or signatures.

## Verification and compatibility algorithm

A consumer performs these checks in order and stops on the first stable category:

1. Parse one explicitly supplied fixture or value; reject duplicate or unknown
   fields and unsupported versions. The validator uses a fixed file list and
   performs no filesystem discovery.
2. Re-encode the supplied checkpoint prefix and state and verify the manifest's
   canonical input and state digests. Verify manifest lineage references, state
   ordering, active replay ordering, and the resolved-event watermark.
3. Hash the manifest and verify the resume request identifies that exact value.
4. Require exact equality of serialization, projection identity/version, engine
   version, policy identity/version, partition definition/version/keys, complete
   evaluation context, checkpoint event prefix, and checkpoint state digest.
   For `account-set` version `1`, also require every account in the verified
   prefix, checkpoint state, append-only suffix, and declared full-replay state
   to belong to the partition keys. Keys with no non-zero sparse state remain
   valid; data for an undeclared key does not.
5. Require a non-empty suffix whose acceptance sequences begin at
   `prefix.last_sequence + 1` and remain contiguous. The first v1 contract keeps
   the evaluation context exact; advancing knowledge, economic, or settlement
   cutoffs requires a rebuilt checkpoint because settlement eligibility may
   change even with no new event.
6. Reject reuse if a suffix correction, cancellation, or reversal targets any
   record in the checkpoint prefix. Also reject a suffix payload whose
   `(effective_at, acceptance_sequence)` is not strictly after the resolved-event
   watermark. These are late lifecycle knowledge, not an ordinary suffix.
7. Only after those checks may an engine apply the ordinary suffix to the
   checkpoint. The authoritative engine, not this validator, computes the
   resulting financial state. Its declared canonical state and lineage must
   equal the full replay result.

This rule is intentionally conservative. A late correction replaces its target;
a cancellation removes it; a reversal retains the target and introduces a new
terminal offset at its own economic time. None is treated as a generic arithmetic
inverse of checkpoint state. The affected partition is rebuilt from inception or
from an earlier verified checkpoint whose prefix and resolved-event watermark
precede the late knowledge. The `late-correction.json` fixture demonstrates a
cash value changing from 1,000 to a replacement 1,200: incremental output is
absent, reuse reports `late_lifecycle_knowledge`, and only the full-replay state
is declared.

The compatible fixture fixes one context and starts with 100,000 USD and an
80-share buy at 55, producing 80 shares, 100,000 settled cash, and a 4,400
payable. Its ordinary suffix adds 2,000 cash and a 20-share sale at 60, producing
60 shares, 102,000 settled cash, the existing 4,400 payable, and a 1,200
receivable. Its full-replay state and lineage are byte-for-byte equal to the
declared checkpoint-plus-suffix result.

## Stable diagnostic categories

The executable contract emits these categories:

| Category | Meaning |
| --- | --- |
| `schema_shape` | Missing, unknown, or ill-typed field; invalid closed variant; or inconsistent duplicated field. |
| `unsupported_version` | Unknown fixture, value, byte, manifest, resume, or digest version/algorithm. |
| `canonical_encoding` | Value cannot be represented by the exact LCB1 and scalar-normalization rules. |
| `digest_mismatch` | Canonical bytes do not match a vector or a claimed input, state, or manifest digest. |
| `duplicate_identity` | A record, economic origin, state key, lineage reference, or vector identity repeats. |
| `deterministic_ordering` | Acceptance, recorded-time, replay, state, partition, or explicit-input order is invalid. |
| `lineage_reference_missing` | A causal, active, lifecycle, or source lineage reference is missing or inconsistent. |
| `incompatible_projection` | Projection identity or version differs. |
| `incompatible_engine` | Engine version differs. |
| `incompatible_policy` | Policy identity or version differs. |
| `incompatible_partition` | Partition identity, version, or keys differ, or a record/state account lies outside the declared account-set. |
| `incompatible_context` | A cutoff or explicit reference/price/calendar/rounding/FX input differs. |
| `incompatible_prefix` | The requested checkpoint prefix is not the verified manifest prefix. |
| `prefix_continuity` | The inclusive prefix or append-only suffix has a gap or wrong boundary. |
| `late_lifecycle_knowledge` | A suffix targets prefix lifecycle knowledge or sorts at/before resolved checkpoint state. |
| `incompatible_account` | A correction, cancellation, or reversal crosses account identity. |
| `incompatible_event_relationship` | A lifecycle edge changes economic identity, event type, natural key, reversal terms, or terminal-action policy. |
| `conflicting_lifecycle_successor` | More than one lifecycle record directly targets the same predecessor. |

Diagnostic prose is explanatory and may grow; category strings are the portable
contract.

## Fixture and validator responsibilities

`canonical-vectors.json` pins the LCB1 grammar (including the unsigned 64-bit
array-count field and its maximum `ff ff ff ff ff ff ff ff` vector),
representative money and provenance values, and the maximum public unsigned
lifecycle sequence. Its
named values are closed schemas: the validator applies money and provenance
shape/version rules before accepting matching bytes and digests.
`valid-append.json` covers canonical lifecycle input,
positions, cash, settlement, a verified checkpoint, an ordinary suffix, equality
of full and resumed state/lineage, and incompatible projection, engine, policy,
context, partition, prefix, schema, and hash cases. `late-correction.json` pins
the conservative invalidation and rebuild rule.

`test_serialization_checkpoint_contract.py` validates exact shape, versions,
scalar normalization, ordering, canonical bytes, hashes, round trips, manifest
binding, compatibility, prefix continuity, lineage, and stable diagnostics. It
accepts explicit values and named fixture paths only. It has no network,
database, environment, filesystem discovery, clock, or hidden input access. It
derives context-selected lifecycle heads solely to verify declared lineage and
the watermark. It does not calculate a position, cash balance, settlement
obligation, correction delta, cancellation, or reversal. That avoids creating a
second financial projection engine in Python.

## Deliberately deferred

This increment does not select a storage medium, persistence service, decoding
API, arbitrary-schema runtime, checkpoint-manifest C++ API, platform adapter,
journal policy, production schema, migration process, compression, signature
scheme, Merkle structure, streaming frame, or release behavior. General
advancing-context incremental replay, partial-partition repair, an empty-event
checkpoint, and additional event/projection variants require later versioned
contracts and fixtures. There is no unresolved encoding default inside the
covered v1 values: unsupported types or versions are rejected rather than
guessed.
