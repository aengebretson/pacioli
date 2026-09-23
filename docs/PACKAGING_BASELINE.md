# LUCA packaging baseline

This audit covers task O1-T01 at source commit
`2af21ce91cdc299d00717d9cca462a17e229ec59`.

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

## Remaining package and platform gaps

- The domain-oriented `luca::ledger`, `luca::portfolio`, and
  `luca::reconciliation` targets described by the Slice 1 design are not part
  of this bounded increment.
- Nested `add_subdirectory` use still defaults `PACIOLI_BUILD_TESTS` to `ON`,
  requires Python, and enables testing. The root build also still sets
  directory-wide C++ standard variables. Parent-build isolation remains
  incomplete.
- The CMake project and option names still use the historical `pacioli` /
  `PACIOLI_*` identity, and the legacy forwarding header remains present.
- No package-manager recipe, binary artifact, ABI guarantee, repository rename,
  tag, or public release is created here.
- Local verification covers the compilers actually available in the assigned
  environment. GCC is available; Clang and MSVC are not installed here, and no
  existing compiler CI matrix was present at the inspected commit.

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
ctest --preset dev                  13/13 passed
cmake --preset release              passed
cmake --build --preset release      passed
ctest --preset release              13/13 passed
```

Both CTest passes include `luca_package_consumer_test`, which performs the
install and `find_package` sequence described above. Compiler/platform coverage
not present in this environment remains explicit rather than inferred.
