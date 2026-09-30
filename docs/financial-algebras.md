# Financial algebras and reporting projections

LUCA is a framework of explicit financial algebras over immutable evidence.
Normalization interprets source records, an ordered fold resolves lifecycle
knowledge, maps produce valued contributions or journals, reductions combine
compatible results, and comparisons produce breaks against separate observations.
A **projection** is a named, versioned deterministic derivation such as positions,
cash, settlement obligations, journals or an application-owned report.

## Public declaration API

Include `<luca/financial_algebra.hpp>` and link `luca::ledger` (or a domain target
that depends on it). The header is additive; existing financial APIs retain their
concrete types and behavior. No umbrella header change is required.

`FinancialAlgebraDescriptor::create(Definition)` returns
`std::expected<FinancialAlgebraDescriptor, FinancialAlgebraDeclarationError>`.
The descriptor owns every string, port, key and law domain; `definition()` provides
const access. Copying the input definition then changing or destroying it cannot
change the descriptor. It contains no callable, registry, plugin loader, runtime
execution graph or generic composition validator.

| Definition field | Meaning and structural validation |
| --- | --- |
| `kind` | `FinancialOperationKind`: normalization, map, ordered_fold, reduction or comparison. Invalid enum values are rejected. |
| `operation_id`, `operation_version` | Stable semantic operation identity and version, both nonempty tokens. |
| `policy_id`, `policy_version` | Explicit policy identity/version, also nonempty tokens; there is no implicit default financial policy. |
| `inputs`, `output` | Owned `FinancialAlgebraPort` role/type-name tokens. Inputs must be nonempty with unique roles. A comparison has exactly distinct `projected` and `observed` roles. Type names describe ports; they do not dynamically validate C++ types. |
| `ordering`, `ordering_keys` | `FinancialOrdering` is not_applicable, ordered or unordered. Ordered requires nonempty distinct keys; other choices require no order keys. An ordered_fold must be ordered. This is input evaluation order, not output presentation order. |
| `partitioned`, `partition_keys` | Partitioned requires nonempty distinct key tokens; unpartitioned requires empty keys. Completeness for a particular financial domain remains the concrete operation's responsibility. |
| `laws` | Unique `AlgebraLawDeclaration` values with law, status and owned domain text. Missing laws read as unknown through `law_status`. |

Tokens reject ASCII whitespace/control bytes. Domain text is explanatory prose;
a claimed law must contain non-whitespace content. Typed errors distinguish invalid
enums/identifiers/ports/ordering/partition keys, duplicate laws, missing law domains
and unsupported claims. Validation does not interpret the prose or prove the keys
complete. For example, a descriptor can structurally name only `account`; the
actual cash reducer rejects that incomplete account/currency partition contract.

`AlgebraLaw` names identity, associativity, commutativity, invertibility and
distributivity. `AlgebraLawStatus` distinguishes unknown, claimed and not_applicable.
This first declaration boundary accepts claims only for a reduction's identity,
associativity and commutativity. Inverse and distributive claims need further
operand contracts and are rejected, as are law claims for other operation kinds.
Unknown/not-applicable declarations can document those other kinds without
claiming execution equivalence. This conservative API restriction is not a claim
that no other mathematical laws can ever apply to them.

**Declaration metadata is not proof. Unknown laws never authorize optimization;
claimed laws also require independently established preconditions and evidence.**
There is deliberately no `proven` flag or optimizer permission API. An unordered
label alone does not license a host to reorder a fallible computation.

## Exact arithmetic has a bounded domain

The existing `reduce_exact_cash`, `merge_exact_cash` and `exact_cash_zero` operations
operate on one account/currency key, scale-6 money, explicit operation/policy
versions and a complete `ExactCashEvaluationContext`. Nonidentity contributions
require event and source-record lineage. Event identities must be disjoint;
source-record sets are sorted and deduplicated. The identity has zero amount and
empty lineage. No conversion or rounding occurs in the reducer.

Identity, associativity and commutativity apply to compatible contributions only
when every checked intermediate sum in every ordering/grouping being compared
is representable. Signed fixed-width addition is not a total algebra over all
`int64` values. In scaled units, `[INT64_MAX, 1, -1]` fails in that order while
`[INT64_MAX, -1, 1]` succeeds, despite their equal mathematical final sum. A
successful sequential run does not establish safety of arbitrary partitioning.
A sufficient arithmetic restriction is that the sum of absolute input magnitudes
fits in `INT64_MAX`, but computing that bound must itself use safe arithmetic;
the descriptor does not compute or verify it.

Lifecycle correction/cancellation requires ordered resolution, not subtraction
of old state. A journal map does not inherit distributivity from a later additive
balance reduction. Comparison is directional: projected and observed ports have
different authority, and `observed - expected` is not symmetric. Reports cannot
silently merge currencies, net payable and receivable magnitudes, or convert
observations into accepted ledger events.

## Independent custom cash-report projection

[`examples/financial-algebra-report`](../examples/financial-algebra-report/README.md)
contains an external-style C++23 consumer with an isolated CMake project.
`custom_report::project_cash_report` consumes explicit exact-cash partials,
separate observations and an existing comparison contract. It groups by the
complete `(account, currency)` key and delegates all monetary calculations and
compatibility validation to the original `reduce_exact_cash` and
`compare_exact_cash` APIs. It preserves input order within each key; it does not
apply the descriptor's law claims as optimization permissions.

The report is a map over a complete supplied batch, identified as
`example.cash-report@1` with presentation policy
`example.cash-report.presentation@1`. It contains sorted account/currency totals,
separately retained observations, the exact comparison result, and the reduction
declaration. Its reduction contract uses `reduce.cash.exact@1` and
`exact-cash-sum@1`; the comparison retains its caller-supplied operation/policy
version and full context. It rejects repeated event lineage across report keys
as well as within a key, avoiding duplicate economic contributions.

Every total retains source-event and source-record IDs and its complete reduction
trace. Every observation retains all supplied provenance, metadata and cutoffs.
Breaks retain those authority roles separately; exact matches also retain both
sides in the report even though the comparison emits no break. The example prints
all this available evidence and explicit scaled amounts. Empty input means no
projected keys, not invented zero balances for unspecified accounts.

The synthetic input already contains valued cash contributions, with an intended
USD total of 800.000000 versus a 790.000000 observation and a -10.000000 difference.
It carries no price/FX source, lifecycle chain or upstream valuation policy; the
report does not manufacture them or claim end-to-end valuation/lifecycle lineage.
This is an extension example, not a second calculator or an authoritative cash
projection from raw events. Its output is illustrative text, not a canonical wire
format or accounting compliance claim.

## Future typed adapters and composition

The intended signatures remain small and explicit: a map receives a typed value
and policy; an ordered fold receives initial state, ordered inputs and context;
a reduction receives compatible contributions and a named merge rule; a
comparison receives distinct projected and observed ports. A generic callable
interface needs a separate bounded proposal, not an inferred runtime here.

Actual composition must check typed ports, dimensions, currency, complete cutoffs,
engine and applicable policy versions, lifecycle resolution, and complete financial
partition keys. Equal descriptor names do not establish any of those facts.
Operation-specific contracts remain authoritative for validation and errors.
See the [transformation contract](transformation-contract.md) for current API
inventory, semantic fixtures and invalidation rules.

## Verification boundary

`tests/unit/financial_algebra_test.cpp` authors declaration validation/ownership,
report evidence, exact comparison, context/currency/partition incompatibility,
duplicate lineage, deterministic repetition, bounded identity/partition equality,
and intermediate-overflow counterexamples. Compilation does not establish these
assertions: their execution is pending while automated testing remains paused.
Root test registration is an integration step owned by the package lane.
