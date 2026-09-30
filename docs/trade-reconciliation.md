# Exact trade comparison and CSV observations

F1 v1 is a deterministic **comparison projection** over lifecycle-derived trade
rows and independent statement observations. It reports exact matches and
explainable breaks; it does not modify authoritative state. Its financial algebra
has an explicit restricted domain, not a general fuzzy matching or reconciliation
service. Direct includes are `luca/reconciliation/trade_reconciliation.hpp` and
`luca/adapters/trade_csv.hpp`. Existing position, cash, lifecycle and canonical
serialization APIs are unchanged.

## Public operations and their domain

1. `TradeComparisonContext::create(economic_as_of, recorded_through,
   trade_date_from, trade_date_through, accounts)` validates explicit inclusive
   trade-date coverage and a nonempty, unique account set. Account order is
   canonicalized. The two timestamps are the baseline lifecycle resolver's
   inclusive economic and knowledge cutoffs. The fixed policy identity is
   `luca.trade-comparison.exact`, version `1`.
2. `project_trades(ledger, mappings, context)` resolves the supplied read-only
   `LifecycleLedger` at those exact cutoffs. Each active equity in a covered
   account needs a `TradeIdentityMapping` with stable economic ID, selected
   active record ID, external key, supplied trade date and mapping provenance.
   Dates are explicit because an economic timestamp does not define a source's
   trading calendar or timezone. Map even trades outside the date interval, so
   coverage can be selected using supplied dates. Cash and other accounts are
   excluded. Extra mappings, missing mappings, stale record bindings and
   duplicate mappings/keys reject the whole operation.
3. `TradeObservation::create(key, terms, context, source_record, provenance)`
   validates coverage and requires provenance to identify exactly that owned
   statement-row source record. CSV ingestion supplies this evidence automatically.
4. `reconcile_trades(expected, observed, context)` rejects context disagreements,
   duplicate keys and ambiguous identities before returning an owned
   `TradeReconciliationReport`. Entries are sorted by `(account,
   external_trade_id)` and include exact matches. A mismatch lists all differing
   fields in this order: instrument, quantity, price, currency, trade date,
   settlement date. Missing/unexpected entries carry only the evidence that
   exists. An empty side explicitly means no rows in the caller-declared
   coverage; the function cannot certify completeness of external evidence.

`TradeProjectionRow` and `TradeObservation` are separate validated value classes,
with read-only accessors. A projected row can only be constructed by
`project_trades`, which reuses lifecycle resolution; it does not select or repair
lifecycle chains independently. Calling the resolver internally matters because
the baseline `LifecycleResolution` exposes references, but no cutoff metadata.
Rows and reports own their values and copy the complete selected lifecycle
records/provenance and mapping provenance. Reversals also retain the target's
resolved lineage. They survive destruction or subsequent mutation of caller
ledgers, mapping arrays, CSV text and observation arrays. Authoritative source
payloads remain referenced through the baseline provenance IDs; they are not
silently fetched or invented. Observation evidence includes an owned SourceRecord
and payload digest. There is no conversion from observations to ledger events.

`TradeReconciliationError` contains a typed code, input side and available key,
record ID and value error. Reconciliation validates projection rows then
observations, each in sorted-key order. Projection mapping diagnostics follow
mapping input order, lifecycle active-event order, then unused economic IDs in
sorted order. Repeated identical inputs have stable diagnostics. Equal duplicate
payloads are rejected just like contradictory payloads. One projected economic
or active-record identity cannot occupy multiple keys; one observation source-row
identity cannot occupy multiple keys. IDs are unique in the supplied identity
scope; cross-ledger namespace management belongs to callers.

## Exact semantics and operation laws

A key is a caller-normalized account plus externally supplied trade ID. Identity
strings are nonempty scalar UTF-8, contain no ASCII controls/DEL and have no
leading/trailing ASCII spaces. Matching is case-sensitive and byte-exact. There
is no whitespace trimming, Unicode normalization, case folding or symbol alias
lookup. Normalize source aliases explicitly before constructing mappings/CSV;
canonically equivalent Unicode spellings are distinct unless callers map them.
A matching price/date/quantity or a coincident internal ID never creates a key.

Quantities are signed, nonzero, scale-8 exact values; positive means buy, negative
means sell. Prices use the existing scale-8 exact type and must be nonnegative;
zero prices are allowed. Currency uses the existing three-uppercase-ASCII-letter
value, without an added ISO registry. Date values must be valid civil dates.
Settlement dates are supplied facts, with no inferred calendar and no additional
settlement-after-trade constraint. Comparison uses equality only: no monetary
multiplication, subtraction, tolerance, rounding, FX, fees, lot/P&L computation or
legal netting is performed. Even comparisons at signed int64 scaled limits do
not require overflowing arithmetic. Economic and knowledge scopes must be
identical; statement observation time remains separate audit evidence.

For validated unique-key inputs under one context and policy:

- Reordering either input preserves the report (sorted output).
- Comparing identical inputs repeatedly preserves results and evidence.
- Empty input on both sides gives an empty report with the supplied context.
- Comparing independent disjoint key partitions and combining/sorting their
  entries equals one comparison only when context/policy agree and all key and
  evidence-identity uniqueness requirements also hold globally.

There is no general associative or commutative statement-matching law, no inverse
operation and no numeric reduction here. Overlapping partitions require global
validation; concatenation is not a deduplication rule. Lifecycle resolution is
ordered and remains upstream. A correction replaces its authoritative payload
only through that existing resolver. Original and corrected statements are
separate comparisons, not instructions to append or replace financial events.

## Closed CSV v1

`luca::adapters::parse_trade_csv(text, source, context, limits)` is pure, receiving
all bytes and context explicitly. It returns an owned observation vector or one
`TradeCsvError`; no partially parsed vector is exposed. It has no filesystem,
network, storage or provider access and no extra dependencies.

The exact decoded header and column order are:

```csv
external_trade_id,account,instrument,quantity,price,currency,trade_date,settlement_date
```

The header may use the same quoting as data fields. Missing, extra, duplicated,
renamed or reordered columns are rejected. Input is strict scalar UTF-8 without
a BOM. Separator is comma. Double-quoted fields allow commas and doubled double
quotes; quotes must enclose the whole field, with no trailing whitespace. Records
use LF or CRLF (either is accepted), with optional final newline. Bare CR, embedded
record newlines, NUL, blank records and unterminated/stray quotes are rejected.
Header-only input is an explicit empty statement for the supplied coverage.

Decimals use `-?[0-9]+(\.[0-9]{1,8})?` and existing checked int64 scale-8 parsing.
Leading zeroes are accepted. Plus signs, exponents, grouping, whitespace, omitted
integer/fractional digits, excess precision and overflow are rejected; nothing is
rounded. Negative zero quantity is zero and rejected; negative zero price is
exact zero. Dates use valid `YYYY-MM-DD` with years 0001–9999. Currency is exactly
three uppercase ASCII letters. Identity fields obey the key rules above.

Default and hard maximum limits are 8 MiB input, 100,000 data records, 8,192 bytes
per record excluding CRLF/LF terminators, and 1,024 decoded bytes per field.
`TradeCsvLimits` can lower these positive limits, never raise them. Header fields
are subject to the same field/record caps. Source system ID, statement ID, digest
algorithm and digest value are each bounded at 1,024 bytes. Context and supplied
source/mapping evidence are caller-owned trusted configuration; output storage
also depends on their sizes. This is an in-memory bounded batch parser, not a
streaming importer.

`TradeCsvSource` requires a source system ID, statement SourceRecordId, payload
hash and observed timestamp. Row identities are length-framed strings:

```text
trade-csv-v1:<source byte length>:<source>:<statement byte length>:<statement>:<physical row>
```

Header is physical row 1 and the first observation is row 2. Length framing
prevents delimiter collisions. Row evidence retains the supplied payload digest,
source identity, statement reference, external trade ID and observation time;
normalization provenance is `luca.trade-csv` version `1`. Repeat parsing the same
text/source/context produces the same values and identities. Corrected statements
must have distinct immutable statement IDs supplied by the caller. Reusing a
statement ID with different bytes is not detected across calls. The digest is
opaque and preserved, not calculated or verified; parsing does not authenticate,
persist or implement cross-call deduplication. Raw bytes remain caller evidence.

CSV errors identify physical row and schema column (1-based); zero means whole
input/record. UTF-8 and source/limit checks precede record scanning. On a data row,
syntax/value/coverage validation precedes duplicate-key rejection. Identical or
conflicting duplicates both return `duplicate_key`. Enum diagnostics are C++ API
values, not a new canonical serialization schema.

## Evidence and pending acceptance

The independent project under `examples/trade-reconciliation/` compiles the
public headers, correction example and focused authored unit executables without
root custom conformance generation. Its README describes compilation and pending
checks. `tests/conformance/trade-reconciliation/` contains portable financial
inputs/expectations and eight raw CSV fixtures. Tests cover exact and per-field
mismatch, opposite sides, multiple currencies, missing/unexpected rows, corrected
independent evidence, duplicates/ambiguity, context mismatch, deterministic order,
owned lineage and parser failures/bounds. Test execution is paused; compilation
is not financial acceptance. Root adapter include/install/target setup and test
registration are coordinator integration work recorded in the runtime
`INTEGRATION.md`. Real custodian/platform acceptance, persistence replacement
policy, portable hosts and wider matching are outside this increment.
