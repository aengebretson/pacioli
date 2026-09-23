# LUCA packaging baseline

The initial install/export audit covers task O1-T01 at source commit
`2af21ce91cdc299d00717d9cca462a17e229ec59`. The O1-T02 parent-consumer
implementation commit `5414bb017036e06a4c6489379eba172548cf2a36` was originally
based on `38d9caba2e8106aec27ab0a6178ef81fffdfaa01`. This bounded repair applies
that implementation to current-main base
`23fb82fafd64d056aa17be1708851e41c953133c`.

## Canonical identity inspected

- The checked-out Git remote is `https://github.com/aengebretson/pacioli.git`.
- The repository README identifies the product as Pacioli LUCA, while the
  canonical C++ headers and types use the `luca` namespace.
- The root CMake project is still named `pacioli` at version `0.1.0`. This task
  does not rename the repository or project and does not publish a release.

## Consumer behavior

Before this task, the source tree exposed one header-only CMake target named
`pacioli`. It provided the ledger, portfolio, reconciliation, and legacy
forwarding include roots directly from the source checkout. It had no CMake
namespace alias, install rules, exported targets, package configuration, or
out-of-tree consumer test.

This task adds the following bounded package surface while retaining the
existing source target:

| Consumption mode | Public target | Status |
| --- | --- | --- |
| `add_subdirectory` | `pacioli` | Existing target retained |
| `add_subdirectory` | `luca::luca` | Implemented umbrella alias |
| `find_package(Luca CONFIG REQUIRED)` | `luca::luca` | Implemented installed export |
| Either mode | `luca::ledger` | Missing |
| Either mode | `luca::portfolio` | Missing |
| Either mode | `luca::reconciliation` | Missing |

The installed target requires C++23 and exposes only the install prefix's
include directory. Installation includes the canonical `luca/...` public
headers and the existing `pacioli/ledger.hpp` compatibility header. Package
metadata is installed under `lib/cmake/Luca` (or the platform-specific GNU
install library directory).

`tests/package_consumer` is an independent CMake project. The main build's
CTest entry installs LUCA to an isolated prefix, configures that consumer with
only the prefix through `CMAKE_PREFIX_PATH`, links `luca::luca`, builds it, and
runs a deterministic public-API cash projection. The expected output is:

```text
cash_scaled=125000000 currency=USD
```

## Parent-project behavior

`PACIOLI_BUILD_TESTS` now defaults from CMake's `PROJECT_IS_TOP_LEVEL` state.
It remains `ON` for a direct top-level LUCA configuration and defaults to
`OFF` when an unrelated project adds LUCA with `add_subdirectory`. Benchmarks
continue to default to `OFF`. A parent can explicitly opt into the Luca tests
with `-DPACIOLI_BUILD_TESTS=ON`; this does not change the installed
`find_package(Luca)` configuration or exported `luca::luca` target.

`tests/parent_consumer` is an independent CMake project that disables Python3
package discovery, adds the LUCA source tree in a separate binary directory,
links `luca::luca`, and runs the same deterministic public cash-projection
result used by the installed-package smoke test. Its default CTest inventory
contains only `luca_parent_consumer_run`; it contains no LUCA unit,
conformance, benchmark, or installed-package consumer tests. The regression
driver also performs a separate configure with the explicit test opt-in and
checks that the LUCA smoke, conformance, and installed-package consumer tests
are then present.

## Remaining package and platform gaps

- The domain-oriented `luca::ledger`, `luca::portfolio`, and
  `luca::reconciliation` targets described by the Slice 1 design are not part
  of this bounded increment.
- The CMake project and option names still use the historical `pacioli` /
  `PACIOLI_*` identity, and the legacy forwarding header remains present.
- The source project still sets directory-wide C++ standard variables in its
  own CMake directory rather than expressing every setting only on targets.
- No package-manager recipe, binary artifact, ABI guarantee, repository rename,
  tag, or public release is created here.
- Local verification covers the compilers actually available in the assigned
  environment. GCC is available; Clang and MSVC are not installed here, and no
  existing compiler CI matrix was present at the inspected commit.

These bounded install/export and parent-consumer checks do not establish the
remaining target namespaces, cross-compiler coverage, or completion of O1.

## Verification environment

- CMake 3.25.1
- Ninja 1.11.1
- GCC/G++ 12.2.0 on Linux
- Clang: unavailable in the assigned environment
- MSVC/Windows: unavailable in the assigned environment

Evidence collected in this environment:

```text
cmake --preset dev                  passed
cmake --build --preset dev          passed
ctest --preset dev                  14/14 passed
cmake -S . -B build/top_level_default_verification
      -G Ninja -DCMAKE_BUILD_TYPE=Debug
                                       passed
cmake -LA -N build/top_level_default_verification
                                       PACIOLI_BUILD_TESTS=ON;
                                       PACIOLI_BUILD_BENCHMARKS=OFF

cmake -S tests/parent_consumer
      -B build/parent_consumer_verification
      -G Ninja -DLUCA_SOURCE_DIR=$PWD -DCMAKE_BUILD_TYPE=Debug
                                       passed; no Python3 discovery
cmake --build build/parent_consumer_verification
                                       passed
cmake -LA -N build/parent_consumer_verification
                                       PACIOLI_BUILD_TESTS=OFF;
                                       PACIOLI_BUILD_BENCHMARKS=OFF
ctest --test-dir build/parent_consumer_verification -N
                                       one parent test listed
ctest --test-dir build/parent_consumer_verification --output-on-failure
                                       1/1 passed
./build/parent_consumer_verification/luca_parent_consumer
                                       cash_scaled=125000000 currency=USD

cmake -S tests/parent_consumer
      -B build/parent_consumer_opt_in_verification
      -G Ninja -DLUCA_SOURCE_DIR=$PWD -DCMAKE_BUILD_TYPE=Debug
      -DPACIOLI_BUILD_TESTS=ON
      -DLUCA_PARENT_CONSUMER_ALLOW_PYTHON=ON
                                       passed
ctest --test-dir build/parent_consumer_opt_in_verification
      --show-only=json-v1             listed the parent test plus all 14 LUCA tests

ctest --preset dev
      -R 'luca_(package|parent)_consumer_test' --output-on-failure
                                       2/2 passed
git diff --check                     passed
rg -n '[[:blank:]]+$' CMakeLists.txt docs/PACKAGING_BASELINE.md
      tests/parent_consumer           no matches
```

The top-level CTest pass includes `luca_package_consumer_test`, which performs
the install and `find_package` sequence described above, and
`luca_parent_consumer_test`, which performs the default and opt-in nested
configuration checks. Compiler/platform coverage not present in this
environment remains explicit rather than inferred.
