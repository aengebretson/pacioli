# Settlement-date accounting projection cases

`walkthrough.json` is a focused, hand-reviewable extraction of the existing
[accounting-foundations fixture](../accounting-foundations/valid-cash-equity-lifecycle.json).
It preserves the exact source/lifecycle inputs, expected settlement-date journal
facts, five evaluation cutoffs, balances, portfolio states, and side-by-side
trade-date entry selections. It introduces no canonical serialization schema.
Decimal financial values remain strings. The original fixture is the reference
for the policy; this extraction is not a new accounting-policy version.

The dedicated C++ [unit source](../../unit/settlement_date_projection_test.cpp)
uses these same four lifecycle records and five evaluations, supplied by the
[synthetic example fixture](../../../examples/settlement-date-accounting/fixture.hpp).
Its assertions cover exact journal amounts, identity, ordering, balance,
lineage, version/context metadata, replay, and portfolio agreement. It also
projects the original purchase with an independently advanced June 4 settlement
cutoff to exercise `sd.trade-v1.settlement` at exactly `5000.000000 USD`.
The unit source does not parse JSON; no new parser dependency is introduced.
These files are not registered with the generic conformance loader, whose
closed schema is different. Registration instructions are in the worker handoff.

Additional authored cases in that unit source:

| Input or operation | Expected result |
| --- | --- |
| Contribution, settlement cutoff before effective date | Immediate debit cash / credit contributed capital |
| Purchase before settlement | No entry; active and source identities retained |
| Correction before settlement | Original and correction evidence retained; no entry |
| Reversal before settlement | No reversal entry; existing securities remain recognized |
| `0.00000001 * 150` and `0.00000001 * 250` | Both half-even round to `0.000002 USD` |
| `0.00000001 * 50` | `unsupported_event` (rounds to zero), also while deferred |
| Zero contribution, withdrawal, ordinary sell, zero price | `unsupported_event` |
| EUR cash or equity | `unsupported_currency`, also while deferred |
| Maximum quantity times maximum price | `arithmetic_overflow`, also while deferred |
| Settlement before trade date | `invalid_context` |
| Invalid settlement cutoff; selected evidence beyond economic/knowledge cutoff | `invalid_context` |
| Cash lifecycle reversal | `invalid_reversal_treatment` |
| `trade-record-v1` and `trade-v1` aliases | `journal_invariant`, including both deferred or only one recognized |
| Partial equity reversal | Lifecycle acceptance rejects before projection |
| Exact reversal of ordinary sell | Whole projection rejects unsupported original sell |
| Settlement order differs from economic order | Presentation by recognition date then acceptance sequence |
| Identical settlement dates with reversed lexical IDs | Acceptance sequence wins |
| Individual versus batch acceptance; repeated projection | Equal owned results |
| Destruction of input ledger | Result lineage remains owned |
| Lifecycle cancellation | Removed active event; no inferred compensating journal |
| Empty resolved set | Empty entries and selected identities |

Malformed order, absent reversal targets, and corrupted lineage cannot be
constructed through the public lifecycle resolver. The projection retains
explicit defensive validation without adding test-only access to private state.
All software tests and fixture execution remain **unexecuted** under the pause.
Compilation is not evidence that these acceptance cases pass.
