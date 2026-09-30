# O5 — Financial algebras and reporting projections

Status: coordinator-authored implementation design, 2026-09-30. Baseline: OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. The user explicitly reaffirmed algebra concepts and projections for reporting; that language is the architectural direction.

## Framework and baseline

LUCA is a framework of small, explicit financial algebras over immutable evidence. Normalization produces typed canonical evidence; an ordered fold resolves lifecycle knowledge; maps create valued contributions or journals; reductions combine compatible results; comparisons generate reconciliation breaks. Reporting projections derive positions, cash, obligations, journal balances, and custom reports. Execution hosts manage scheduling, storage, permissions, and transport outside these operations.

`docs/transformation-contract.md` already declares this vocabulary and its composition rules. Public `reduce_exact_cash`, `merge_exact_cash`, `exact_cash_zero`, and `compare_exact_cash` provide a concrete bounded example with policy/context/lineage. The baseline also contains lifecycle-aware portfolio and trade-date journal projections. The document's interface inventory still describes those later additions as absent; it must be corrected without claiming that a generic composition runtime already exists.

## Bounded first-wave increment

Add a small, additive public declaration header, proposed as `luca/financial_algebra.hpp`, and an independent custom-report example. Prefer plain owned values and explicit functions over inheritance, dynamic plugins, type-erased execution graphs, or expression languages. The declarations identify operation class, stable operation/version, input and output roles, explicit policy identity, ordering requirement, partition keys, and claimed laws with a stated domain. Proposed symbols are `FinancialOperationKind`, `AlgebraLawDeclaration`, and an owned `FinancialAlgebraDescriptor`, plus a validating factory returning a typed declaration error. They describe a financial contract; they do not execute arbitrary operations or certify a mathematical proof.

Use the existing `ExactCashReductionContract` and comparison types directly in the example. A custom cash-report projection can reduce same-key exact cash partials and display account/currency totals with evidence, then compare them to separate observations. Keep financial arithmetic in existing operations. Do not relabel untraced totals as fully lineage-bearing results or invent a price/FX source. Avoid a global metadata envelope that would force changes to all existing APIs.

Document the intended shape of future typed adapters: a map accepts an explicit value and policy; an ordered fold accepts an initial state, ordered inputs, and context; a reduction accepts compatible contributions and a named merge rule; a comparison has distinct projected and observed ports. Any callable generic interface beyond the first additive declaration requires a subsequent bounded proposal.

## Laws, errors, and reporting semantics

Exact cash addition is associative and commutative only over equal account/currency keys with representable checked intermediate sums. The finite overflow domain matters: arbitrary regrouping can change whether a calculation fails. Lifecycle resolution is ordered; cancellation and correction are not inverse operations. A journal map does not become distributive merely because a later balance reduction is additive. Comparisons preserve authority roles and are not symmetric financial operations.

Composition requires compatible typed ports, dimensions, currencies, complete cutoffs, operation policy versions where reuse applies, and complete partition keys. Unknown or unproven laws default to no optimization permission. A report cannot silently merge currencies, net payables and receivables, bypass lifecycle resolution, or reinterpret an external observation as an accepted event.

## Ownership, dependencies, and acceptance

This lane owns the new declaration header, a new custom-report example directory, lane-specific unit source, and `docs/transformation-contract.md` inventory corrections. It does not modify existing financial APIs or root CMake/umbrella exports. It depends only on integrated exact-cash functionality, allowing accounting, replay, and reconciliation workers to proceed independently.

Acceptance requires a readable public contract and a compilable external-style example that makes algebra, projection, context, and evidence visible without adding another calculator. Prepare cases for incompatible context/currency, missing partition keys, and unsupported composition claims only for behavior actually implemented. Software tests and deployment remain paused; planned checks are not acceptance evidence. Later increments can introduce typed reusable composition after concrete use demonstrates the need.
