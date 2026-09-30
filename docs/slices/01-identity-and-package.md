# Slice 1 — LUCA identity and package

**Status:** O1-T04 implementation prepared; runtime and compiler CI verification pending

**Last updated:** 2026-09-30

**Scope:** Open-source LUCA package only

## Purpose and current decisions

LUCA is a standalone C++23 library for financial algebras and projections for
reporting. Immutable evidence, normalized events and ordered replay supply
positions, cash, settlement and accounting views; external observations remain
separate reconciliation inputs. Execution hosts provide storage, scheduling,
network access and presentation outside the financial core.

The [pinned O1 completion design](../oss-program-20260930/designs/01-package.md)
supersedes this slice's earlier proposal to remove legacy names. Compatibility is
required for O1-T04. Existing package capabilities from O1-T01–T03 are preserved:

- CMake project `luca`, C++ namespace `luca`, installed package `Luca`;
- public targets `luca::ledger`, `luca::portfolio`, `luca::reconciliation`, `luca::luca`;
- unchanged source target `pacioli`, forwarding header and `pacioli::Ledger`;
- canonical `LUCA_BUILD_TESTS`, `LUCA_BUILD_TOOLS`, `LUCA_BUILD_BENCHMARKS`, with
  explicit `PACIOLI_*` compatibility aliases;
- source and installed consumers with the same domain graph and C++23 requirement;
- embedded builds defaulting to no LUCA tests, Python discovery, tools or benchmarks;
- relative install/export metadata and an independent consumer example.

There is no financial API change, repository rename, tag, release or ABI guarantee.
A new `LUCA_BUILD_EXAMPLES` option is unnecessary: the walkthrough is a separate
external project. Existing accounting headers remain delivered through
`luca::ledger`; a separate accounting target is a later compatible migration.

## Public dependency boundary

| Target | Direct dependencies |
| --- | --- |
| `luca::ledger` | None |
| `luca::portfolio` | `luca::ledger` |
| `luca::reconciliation` | `luca::portfolio`, `luca::ledger` |
| `luca::luca` | All three domain targets |

Consumers use either `add_subdirectory(third_party/luca)` or
`find_package(Luca 0.1 CONFIG REQUIRED)` and link these targets. They should not
copy core implementation or reference private source paths. The existing
header-only implementation remains behind these targets. Installation includes
canonical `luca/...` headers and the compatibility `pacioli/ledger.hpp` header.
No installed `pacioli` target is added.

## Build option contract

Tests and tools default ON at the top level and OFF when embedded. Benchmarks
always default OFF. Both canonical and legacy names accept cache values and parent
normal variables. When both are defined, their CMake boolean values must agree;
otherwise configuration fails with an actionable message. A legacy-only value
is not copied into a canonical cache entry, allowing the caller to change it
later. Generated readable aliases are normal variables, not stale cache entries.
Existing canonical cache values, including defaults, are defined inputs when
conflicts are checked. Clear the obsolete entry with `-U<name>` when migrating
names; resolve conflicting parent normal variables in the parent itself.

C++23 is a target compile feature. The caller's language-standard settings remain
unchanged. GNUInstallDirs and standard CMake config/export/version helpers retain
relative installation metadata. Presets use the canonical test option and the
schema supported by the declared CMake 3.24 minimum.

## Public walkthrough and acceptance

[examples/package-consumer](../../examples/package-consumer/README.md) is a
complete `find_package` project. It constructs explicit source identities,
USD 1,000 cash and a 10-unit purchase at USD 20, then calls existing position,
cash and settlement projections. An independent USD 790 bank observation yields
an intended USD -10 discrepancy after settlement. No observation mutates the
ledger. The example retains event/source evidence and prints observation lineage.

The example illustrates exact typed financial operations with explicit contexts.
It does not claim universal associativity, commutativity, inverses or partition
independence: laws require compatible domains and representable intermediate
values, and ordered replay remains distinct from unordered reduction.

The package/parent projects cover all four targets, compatibility includes and
the legacy source target. The installed driver moves the prefix before use. The
option matrix covers canonical/legacy values, conflicts, parent normal variables,
cache reconfiguration and defaults. Existing deterministic financial tests remain
required; none are removed to accommodate the standing pause.

See [the packaging audit](../PACKAGING_BASELINE.md) for exact commands and evidence.
GCC 12.2 compilation of the external, installed and embedded consumers succeeded.
No test executable, CTest suite, conformance script or workflow was run. Runtime
output, option-matrix execution, broad financial regressions and cross-compiler
acceptance remain pending until tests resume.

## Compiler and release follow-up

The authored manual-only workflow defines Linux GCC/Clang Debug/Release coverage,
GCC Debug sanitizers, tests, package consumers and benchmark compilation. Jobs are
disabled by default and have no automatic triggers during the pause.

Native MSVC cannot compile the baseline's required signed `__int128` arithmetic.
A separate opt-in Windows probe documents that limitation and uses the same public
consumer; it is expected to fail until a separately reviewed exact arithmetic
portability implementation is available. No fallback numeric representation or
weakened checks are included in package work.

After review and resumed verification, coordinate compatibility deprecation,
repository rename, preview release and package-manager distribution separately.
No such operation is authorized by this implementation handoff. Other parallel
lanes' new headers/tests and target registrations are integrated by the coordinator,
not implicitly folded into O1's packaging change.
