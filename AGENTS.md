# AGENTS.md

## Repository overview

LUCA is a C++ financial ledger and portfolio-state engine.

Read these before making architectural changes:

- `README.md` — project overview and scope
- `docs/design.md` — architecture and design principles
- `docs/roadmap.md` — planned capabilities and sequencing

Do not duplicate those documents here. This file defines how to work in the repository.

## Repository structure

```text
libs/
    ledger/           Canonical events, ledger, provenance, replay
    portfolio/        Position, cash, settlement, and portfolio projections
    accounting/       Accounting and journal projections
    reconciliation/   Observations, matching, aggregation, and breaks
    adapters/         External format and system adapters

apps/
    cli/              Command-line application

bindings/             Language/runtime bindings

tests/
    unit/             Focused implementation tests
    conformance/      Financial-semantic fixtures and replay expectations
    benchmarks/       Reproducible performance benchmarks

examples/             Small end-to-end examples

docs/                 Architecture, roadmap, and technical documentation
```

If a directory does not yet exist, create it only when the assigned work requires it.

## Where code belongs

Put authoritative financial-domain logic in `libs/`.

Use these boundaries:

- Ledger/event identity, provenance, ordering, replay → `libs/ledger`
- Positions, cash, settlement state → `libs/portfolio`
- Journals, accounting policies, P&L accounting → `libs/accounting`
- External observations and reconciliation → `libs/reconciliation`
- FIX, CDM, SWIFT, broker, custodian, CSV, Arrow, Parquet, blockchain integrations → `libs/adapters`
- User-facing command behavior → `apps/cli`

Do not put financial-domain logic in applications, adapters, or infrastructure wrappers.

Adapters translate between external representations and LUCA domain types. External schemas must not leak into the core domain model.

## Architectural constraints

Core financial code must:

- be deterministic for identical inputs
- avoid hidden filesystem, database, network, or RPC access
- avoid global mutable state
- accept dependencies and required data explicitly
- preserve event provenance
- keep external observations separate from authoritative ledger events
- support ordered replay
- remain usable in both single-process and partitioned/distributed execution
- prefer batch-friendly APIs over record-at-a-time I/O

Distributed infrastructure belongs outside the financial core.

Do not introduce Kafka, Kubernetes, service meshes, cloud SDKs, databases, or web frameworks into core libraries unless explicitly required.

## C++ conventions

Use modern C++23.

Prefer:

- value semantics
- RAII
- strong domain types
- `std::span` for non-owning contiguous ranges where appropriate
- `std::expected` for recoverable errors where appropriate
- `std::chrono` types for time
- explicit ownership
- immutable inputs where practical

Avoid:

- raw owning pointers
- hidden singletons
- unnecessary inheritance
- exception-driven ordinary control flow
- implicit numeric conversions in financial code
- premature generic abstractions

Public APIs should be small and explicit.

## Financial numeric rules

Do not use binary floating-point as the default representation for authoritative monetary values.

Do not silently mix:

- currencies
- quantities
- prices
- percentages
- rates

Use explicit domain types or explicit conversions.

Any rounding behavior must be intentional and tested.

## Build

From the repository root:

```bash
cmake --preset dev
cmake --build --preset dev
```

## Tests

Run:

```bash
ctest --preset dev
```

For release validation:

```bash
cmake --preset release
cmake --build --preset release
ctest --preset release
```

When financial semantics change:

- add or update unit tests
- add a conformance fixture when the behavior represents a reusable financial rule
- verify deterministic replay

When fixing a bug, add a failing regression test first when practical.

## Conformance tests

Place end-to-end financial-semantic cases under:

```text
tests/conformance/<scenario>/
```

A scenario should contain explicit inputs and expected derived state.

Prefer fixtures that can eventually be reused by implementations in other languages.

Do not make conformance expectations depend on internal implementation details.

## Benchmarks

Performance work belongs under:

```text
tests/benchmarks/
```

Benchmark changes with reproducible data and report before/after measurements.

Do not claim performance improvements without measurements.

## Debugging

For test failures:

1. run the narrow failing test first
2. reproduce with the smallest relevant fixture
3. inspect event ordering and provenance before changing calculations
4. distinguish source-event errors from projection errors
5. rerun the full test suite after the fix

Do not "fix" reconciliation failures by mutating authoritative state to match an observation.

## Dependencies

Keep dependencies minimal.

Before adding a new dependency:

1. confirm the standard library or existing dependencies cannot reasonably solve the requirement
2. keep the dependency out of core libraries when it is integration-specific
3. document why it is needed

## Git and pull requests

Work in a focused branch.

Keep each PR limited to one coherent change.

Do not mix unrelated refactoring into feature work.

Before finishing:

```bash
git status
```

Confirm only intended files changed.

PR descriptions should include:

- what changed
- why
- tests run
- architectural implications, if any
- known limitations

## Documentation

Update `docs/design.md` when architectural decisions change.

Update `docs/roadmap.md` when project sequencing or planned scope changes.

Do not put temporary task status or release-specific goals into `AGENTS.md`.

## Nested instructions

Subdirectories may contain their own `AGENTS.md` files for specialized rules.

More specific instructions should live close to the code they govern rather than making this root file excessively large.
