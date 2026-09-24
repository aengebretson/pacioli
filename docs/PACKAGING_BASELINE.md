# LUCA packaging baseline

This audit records the O1-T03 package surface on source base
`b0e025f6e37722688315a59d193ad5d671a5e265`. It extends the install/export and
parent-consumer baselines from O1-T01 and O1-T02 without changing public
headers or financial behavior.

## Canonical identity inspected

- The checked-out Git remote is `https://github.com/aengebretson/pacioli.git`.
- The repository README identifies the product as Pacioli LUCA, while the
  canonical C++ headers and types use the `luca` namespace.
- The root CMake project remains `pacioli` at version `0.1.0`. This increment
  does not rename the repository or project and does not publish a release.

## Implemented target surface

The same canonical names are available when the source is nested with
`add_subdirectory` and when an installation is loaded with
`find_package(Luca CONFIG REQUIRED)`:

| Public target | Public domain | Direct interface dependencies |
| --- | --- | --- |
| `luca::ledger` | Canonical values, events, lifecycle, ledger, serialization | None |
| `luca::portfolio` | Position, cash, lifecycle, and settlement projections | `luca::ledger` |
| `luca::reconciliation` | Position and cash observations and reconciliation | `luca::portfolio`, `luca::ledger` |
| `luca::luca` | Compatible umbrella, including the legacy forwarding header | All three domain targets |

Each target requires the `cxx_std_23` compile feature. In a source build, each
domain target exposes only its own `libs/<domain>/include` root and receives
other domains transitively through its interface dependencies. The umbrella
exposes only the compatibility `include` root directly. In an installation,
all four targets expose only the installation's public include directory.

The source target `pacioli` and its `luca::luca` alias remain available to
existing source and parent-project consumers. The export names produce
`luca::ledger`, `luca::portfolio`, `luca::reconciliation`, and `luca::luca` as
installed imported targets. There is deliberately no installed `pacioli`
target; that target name was source-compatible behavior rather than an earlier
installed-package contract.

Installation continues to include the canonical `luca/...` headers and the
existing `pacioli/ledger.hpp` compatibility header. Package metadata is under
`lib/cmake/Luca` (or the platform-specific GNU install library directory).
Only install-interface paths are written to the exported targets, so the
metadata is relocatable and contains no checkout source or build paths.

## Independent installed-package consumer

`tests/package_consumer` is a separate CMake project. Its regression driver
installs LUCA to a newly cleaned isolated prefix, scans every installed CMake
metadata file for source- or build-tree paths, and configures the consumer with
that prefix through `CMAKE_PREFIX_PATH`.

At configure time the consumer proves that all four canonical names are
installed `IMPORTED` targets, checks their C++23 feature, include directory,
and exact domain dependency links, then builds and runs:

- a ledger append linked only to `luca::ledger`;
- the deterministic cash projection linked only to `luca::portfolio`;
- matching position reconciliation linked only to `luca::reconciliation`;
- the existing deterministic cash projection linked to `luca::luca`.

The representative output remains:

```text
ledger_entries=1
cash_scaled=125000000 currency=USD
position_breaks=0
```

Because this project calls only `find_package`, asserts that the targets are
imported, and has no `add_subdirectory` path to LUCA, the domain target names
are proven to come from the installed package rather than in-tree aliases.

## Parent-project behavior

`tests/parent_consumer` remains a separate CMake project. It adds LUCA in a
separate binary directory and verifies that the four canonical names are
non-imported aliases with the same C++23 features, include boundaries, and
dependency graph as the installed targets. It builds and runs the same ledger,
portfolio, reconciliation, and umbrella examples.

`PACIOLI_BUILD_TESTS` still defaults from CMake's `PROJECT_IS_TOP_LEVEL` state.
The parent's default configuration disables Python package discovery and
registers only its four parent-owned consumer tests; no LUCA unit,
conformance, benchmark, or nested consumer test is registered. A separate
configuration with `-DPACIOLI_BUILD_TESTS=ON` and Python enabled confirms the
existing explicit opt-in behavior still exposes the LUCA suite.

## Remaining package and platform gaps

- The CMake project and option names retain the historical `pacioli` /
  `PACIOLI_*` identity, and the legacy forwarding header remains present.
- The source project still sets directory-wide C++ standard variables in its
  own CMake directory in addition to the target compile features.
- No package-manager recipe, binary artifact, ABI guarantee, repository rename,
  tag, CI change, or public release is part of this increment.
- GCC is the only C++ compiler installed in this worker. The Clang C++ compiler
  is unavailable, and MSVC/Windows cannot be exercised from this Linux
  environment. No result is inferred for those missing toolchains.

## Verification environment and evidence

- Linux 6.8.0-139-generic x86_64
- CMake 3.25.1
- Ninja 1.11.1
- GCC/G++ 12.2.0
- Python 3.11.2
- Clang C++ compiler: unavailable
- MSVC/Windows: unavailable

Evidence collected in this environment:

```text
cmake --preset dev
cmake --build --preset dev --parallel 2
ctest --preset dev --output-on-failure
                                      passed; 17/17 tests

cmake --preset release
cmake --build --preset release --parallel 2
ctest --preset release --output-on-failure
                                      passed; 17/17 tests

ctest --preset dev
      -R 'luca_(package|parent)_consumer_test'
      --output-on-failure -V
                                      passed; 2/2 outer checks
                                      package consumer 4/4
                                      parent default 4/4
                                      explicit Luca test opt-in present

clang-format-14 --dry-run --Werror <new consumer C++ sources>
git diff --check
rg -n '[[:blank:]]+$' <allowed changed paths>
                                      passed; no formatting or whitespace errors
```

The package-consumer check performs the clean isolated install, relocation
scan, imported-target property inspection, build, and executions. The parent
check performs the default and explicit-opt-in configurations, source-target
property inspection, inventory checks, build, and executions. Compiler and
platform coverage not installed in this environment remains explicit rather
than inferred.
