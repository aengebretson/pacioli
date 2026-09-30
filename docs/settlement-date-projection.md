# Settlement-date accounting projection

`<luca/accounting/settlement_date_projection.hpp>` adds the concrete
`fixture.settlement-date.v1` policy, version `1`, over the existing immutable
lifecycle resolution and journal factories. This is the second bounded
financial algebra for journal reporting from the
[accounting-foundations contract](accounting-foundations.md). The earlier
contract's statement that only trade-date projection is implemented describes
the prior baseline; this additive header supplies the settlement-date policy.
It is fixture-only accounting, with no production, GAAP, IFRS, tax or NAV claim.

```cpp
const auto resolved = ledger.resolve(recorded_through, economic_as_of);
auto journals = luca::project_settlement_date_journals(
    resolved, luca::SettlementDateProjectionContext{
        recorded_through, economic_as_of, settlement_as_of_date});
```

The return type is
`std::expected<SettlementDateProjectionResult, SettlementDateProjectionError>`.
The header is directly consumable through the existing `luca::ledger` target.
No umbrella header change or separate library target is required to use it.

## Domain and operation laws

The operation is a versioned journal mapping over an ordered, lifecycle-resolved
active set. Lifecycle resolution is the existing causal ordered fold; accounting
does not select heads or reinterpret cancellations. The empty active set maps to
an empty journal set. Identical resolved inputs and context yield equal owned
results. Input evidence and economic effective times remain unchanged.

| Selected event | Recognition | Debit | Credit |
| --- | --- | --- | --- |
| Positive USD contribution | UTC effective date, immediately | `asset.cash` | `equity.contributed-capital` |
| Positive USD equity purchase | Supplied settlement date | `asset.equity-securities` | `asset.cash` |
| Accepted exact-offset reversal of that purchase | Reversal's own supplied settlement date | `asset.cash` | `asset.equity-securities` |

Each entry independently balances in USD. Quantity and price use their existing
exact scales; `abs(quantity) * price` rounds half-even once to six-decimal Money.
For an exact reversal, the validated positive target supplies that magnitude,
avoiding signed absolute-value overflow. Zero-valued postings and valuation
overflow fail. The mapping has no balance reduction API; any subsequent grouped
reduction must check every intermediate addition for overflow. No unrestricted
commutativity, associativity, inverse, partition-independence or arbitrary
reordering law is claimed. An economic reversal is a separate event with its
own recognition date, not an instruction to delete a historical journal.

## Cutoffs and evidence

All three context fields are explicit and inclusive: `recorded_through`,
`economic_as_of`, and the independent date `settlement_as_of_date`. Contributions
are not gated by the settlement date. Equity produces no journal until its
supplied settlement date is at or before that cutoff. No payable or receivable
journal is created. Portfolio positions and open obligations can therefore
exist before accounting recognition; this is the named policy difference.

The caller must resolve with the declared knowledge and economic cutoffs, keep
the ledger alive and unmodified during projection, and provide an appropriate
account/book partition. The projection checks selected active records, causal
lineage knowledge times, head consistency and economic ordering, even for
unsettled events. It validates full prospective entries and identity uniqueness
before excluding deferred entries from the returned result. A failure returns
one typed error and no partial result.

`LifecycleResolution` does not carry its originating cutoff values or an opaque
resolution ID. As with the existing trade-date API, accounting can reject
selected evidence beyond supplied cutoffs, but cannot detect evidence omitted
by a caller who resolved at an earlier cutoff. It does not scan inactive chains
or reconstruct missing heads. This is an existing interface precondition, not a
claim of independent lifecycle verification.

The owned result exposes `policy()`, `evaluation_context()`, `entries()`, ordered
`active_record_ids()`, and first-seen unique `lifecycle_record_ids()`,
`economic_event_ids()` and `source_record_ids()`. Deferred events still appear in
those selected input identities. Version accessors retain the fixture's
`fixture-accounting-engine-1`, `fixture-journal-projection-1`, and
`luca.event-lifecycle.v1` identifiers. Context or policy changes require a new
result; this API implements no checkpoint reuse.

Entry and line lineage exactly follows the existing fixture: a corrected
purchase repeats original and correction record/source identities. A reversal
repeats its own economic/record/source identity and explicitly references the
reversed correction record. The purchase entry retains that target's original
and correction lineage beside the reversal; result identity lists retain the
complete selected union. No historical event, source, or prior result is edited.

## Stable identities and errors

The namespace is `sd.<record-stem>.<phase>`. Fixture stems map
`opening-cash-record` → `opening-cash`, `trade-record-v1` → `trade-v1`,
`trade-record-v2` → `trade-v2`, and `reversal-record-v1` → `reversal`.
Other stems are the unchanged active record ID. Phases are `immediate` (ordinal
0) and `settlement` (ordinal 1); line IDs append `.debit` or `.credit`.
Alias collisions fail even when an affected purchase has not settled. No
trade-date `td.*` identity is reused. Entries sort by recognition date,
acceptance sequence, phase ordinal, then entry identity.

`SettlementDateProjectionDiagnosticCategory` has stable categories
`invalid_context`, `unsupported_event`, `unsupported_currency`,
`invalid_reversal_treatment`, `arithmetic_overflow`, and `journal_invariant`.
The error exposes `category()`, `category_name()`, optional `record_id()` and an
explanatory `message()`. Messages are not stable matching keys. Journal factory
errors map to `journal_invariant` (or `arithmetic_overflow`), retaining the
underlying category in the message.

Withdrawals, ordinary sells, cash reversals, non-USD activity, partial reversals,
fees, FX, taxes, lots, accruals, P&L, calendars, actual or failed settlement,
legal netting and expanded accounting policies remain unsupported. Invalid
partial/multiple reversals are rejected by lifecycle acceptance before this
mapping. Cancellation remains resolver head selection, with no accounting
compensation invented here. Supplied dates model contractual settlement timing,
not evidence of actual payment.

## Fixture and compilation

The [portable expectations](../tests/conformance/settlement-date-projection/README.md)
and [example](../examples/settlement-date-accounting/README.md) use the existing
walkthrough's exact values: `100000.000000` contribution, `5000.000000` original
purchase, `4400.000000` corrected purchase and reversal, `95600.000000` settled
cash before reversal settlement, and `100000.000000` final cash.
The example displays both policies plus portfolio positions, cash and obligations.

The new unit source covers those cases and diagnostic boundaries; its root test
registration is reserved to the coordinator. Existing header-directory install
rules already include the new header. No dependencies or shared interfaces
change. Tests, example execution and conformance verification remain pending
under the user's execution pause; only compilation was performed.
