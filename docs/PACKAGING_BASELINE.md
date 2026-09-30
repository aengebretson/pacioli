# LUCA packaging baseline

## Source and identity

O1-T04 builds on source `20e46a6a0c0744f9591968709adb0eb66aa5a411`, with
batch designs pinned by `08cbc3797b4ab34dc3adbb8a7c2fd30ea29b11ad`.
The package design digest is
`1959abc8df8df733560a2ace0e5f27320f3a8cda633b4994c6e931f917616592`.
The previous O1-T03 audit recorded successful historical tests on
`b0e025f6e37722688315a59d193ad5d671a5e265`; those historical results are not
verification of this working-tree change or the larger current API.

The product is LUCA, the CMake project is `luca` version `0.1.0`, the C++
namespace is `luca`, and the CMake package is `Luca`. The repository remains
`aengebretson/pacioli`. There is no tag, release, repository rename, new ABI
promise, dependency or financial calculation change in this increment.

## Preserved package surface

The four established target names remain available through `add_subdirectory`
and `find_package(Luca 0.1 CONFIG REQUIRED)`. Integration adds the separately
linked `luca::adapters` target without widening the existing umbrella:

| Public target | Public domain | Direct interface dependencies |
| --- | --- | --- |
| `luca::ledger` | Values, events, lifecycle, ledger, serialization; existing accounting headers | None |
| `luca::portfolio` | Position, cash, settlement, lifecycle and replay projections | `luca::ledger` |
| `luca::reconciliation` | Observations and reconciliation | `luca::portfolio`, `luca::ledger` |
| `luca::luca` | Compatible umbrella | Ledger, portfolio and reconciliation |
| `luca::adapters` | Optional external-format adapters, including trade CSV | `luca::reconciliation` |

Each target requires `cxx_std_23`. Source domain targets expose their own include
root and receive other domains transitively. The umbrella's direct source include
root is `include/`. Installed targets expose the install include directory.
Existing accounting headers are still delivered by `luca::ledger`; splitting
accounting into a target is deferred.

The real source target `pacioli`, its `luca::luca` alias, the forwarding include
`<pacioli/ledger.hpp>` and `pacioli::Ledger` remain unchanged. Export names remain
`luca::...`; there is no installed unnamespaced `pacioli` target. Test and benchmark
executable names retain their historical `pacioli_` names so existing automation
can still address them.

Installation uses relative GNUInstallDirs destinations, with metadata under
`${CMAKE_INSTALL_LIBDIR}/cmake/Luca`. Existing header directory install rules are preserved. The integrated adapter
header tree is also installed; consumers opt into its source include root with
`luca::adapters`. Accounting and financial-algebra headers remain on
`luca::ledger`; checkpoint continuation remains on `luca::portfolio`.

## Canonical options and compatibility

| Canonical name | Legacy alias | Top-level default | Parent default |
| --- | --- | --- | --- |
| `LUCA_BUILD_TESTS` | `PACIOLI_BUILD_TESTS` | ON | OFF |
| `LUCA_BUILD_TOOLS` | `PACIOLI_BUILD_TOOLS` | ON | OFF |
| `LUCA_BUILD_BENCHMARKS` | `PACIOLI_BUILD_BENCHMARKS` | OFF | OFF |

`cmake/LucaOptions.cmake` accepts both cache entries and parent normal variables.
An explicit legacy-only value supplies the effective canonical value without
creating a canonical cache entry; repeated legacy-only configuration can change
that value. Otherwise, the canonical name is a standard CMake option. A readable
legacy normal variable reflects the resolved value without inserting an alias
cache entry. If both names are defined, their CMake boolean meanings must agree
(`TRUE` and `ON` agree). Conflicts fail before Python discovery or target setup
and identify both names plus the `-U` cache-removal remedy. Existing canonical
cache defaults count as defined values; clear that entry before switching to a
legacy-only configuration. Parent normal variables must be reconciled in the
parent, not by clearing a cache entry they shadow.

No default parent Python discovery, tools, benchmarks or LUCA tests are added.
C++23 comes from target compile features; the source directory's extension policy
does not change the parent's standard/required/extensions settings. The standalone
example is a separate project and is never injected into an embedded build.
Presets use canonical test options; schema version 5 matches the declared CMake
3.24 minimum (the former schema 6 required a newer CMake).

## Authored acceptance cases — unexecuted

- Existing per-domain installed/embedded consumers preserve the exact dependency
  graph and compile features, plus ledger, cash, reconciliation and replay cases.
- Installed legacy consumer includes the forwarding header via `luca::luca`;
  embedded legacy consumer uses the real `pacioli` source target.
- The parent consumer checks project identity, language-policy isolation, both
  option names and requested test/tool/benchmark targets. Its default configuration
  disables Python discovery; its eight consumer tests are parent-owned. The new
  adapter consumer reads a synthetic trade observation and preserves it as an
  unexpected observation against an empty ledger. Public-header compilation
  covers financial algebras, settlement-date journals, refreshed checkpoint
  results and exact trade reconciliation through their owning domain targets.
- `tests/parent_consumer/options.cmake` covers defaults, canonical and legacy
  ON/OFF options, equivalent boolean spellings, contradictions in both directions,
  parent normal variables, legacy-only cache reconfiguration and top-level defaults.
- Installed regression driver scans exported metadata for source/build paths and
  moves the installation before configuring the consumer against the new prefix.
- The package walkthrough uses deposit and equity-trade inputs, projects cash,
  positions and settlements, then reconciles an independent USD 790 observation
  against USD 800 projected cash. Expected difference: USD -10; input and observation
  source identities remain available. Output expectations are authored, not observed.

## Actual configure/compile/package evidence

Environment: Linux x86_64, CMake 3.25.1, Ninja 1.11.1, GCC/G++ 12.2.0.
Clang is not installed; native Windows/MSVC is unavailable. The worker reported that all commands below completed successfully before
integration. The following counts describe that worker snapshot, not the
additional integration consumer coverage. `OUT` denotes the assigned O1-T04 runtime output directory
`/home/andrew/luca-development/state/maintenance/oss-20260930/oss-package-20260930/output`.
Build products are outside the checkout.

```sh
cmake -S . -B "$OUT/build/package" -G Ninja -DLUCA_BUILD_TESTS=OFF -DLUCA_BUILD_TOOLS=OFF -DLUCA_BUILD_BENCHMARKS=OFF -DCMAKE_BUILD_TYPE=Release
cmake --install "$OUT/build/package" --prefix "$OUT/prefix"
mv "$OUT/prefix" "$OUT/prefix-relocated"
cmake -S examples/package-consumer -B "$OUT/build/example" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$OUT/prefix-relocated"
cmake -S tests/package_consumer -B "$OUT/build/installed" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$OUT/prefix-relocated" -DLUCA_EXPECTED_INSTALL_PREFIX="$OUT/prefix-relocated"
cmake -S tests/parent_consumer -B "$OUT/build/parent" -G Ninja -DCMAKE_BUILD_TYPE=Release -DLUCA_SOURCE_DIR="$PWD"
cmake --build "$OUT/build/example" --parallel 2
cmake --build "$OUT/build/installed" --parallel 2
cmake --build "$OUT/build/parent" --parallel 2
```

One external walkthrough, eight installed consumer targets and seven embedded
consumer targets compiled and linked. The public target checks performed during
consumer configuration succeeded. Installed configuration/build used the relocated
prefix; embedded configuration succeeded with Python discovery disabled. No
program was executed. This is compilation/package evidence, not financial runtime
or deterministic replay acceptance. `git diff --check` also passed.

The root test-enabled build contains a custom conformance fixture generator;
it was not invoked. The inspected consumer projects have no build-time test
execution. No CTest, automated test script, consumer executable, CI, benchmark,
staging or deployment was executed.

## Compiler workflow and outstanding verification

`.github/workflows/package-compilers.yml` is authored only, with no push, PR or
scheduled triggers. Manual dispatch defaults `resume_checks` to false. After the
pause is explicitly lifted it defines GCC 14 and Clang 18 Debug/Release jobs,
root GCC Debug ASan/UBSan flags, root tests, option/consumer checks, a benchmark
compile (not execution), and standalone example compilation. Runner package
availability and these compiler/standard-library combinations are unverified.

The Windows 2022/MSVC job is a separate opt-in capability probe, expected to fail:
`libs/ledger/include/luca/core/detail/wide_integer.hpp` requires signed `__int128`
and rejects native MSVC. No numeric fallback or weakened check is appropriate.
A separate reviewed core-numeric portability change with equivalent exact
arithmetic/overflow/rounding coverage is required before claiming MSVC support.

Pending commands **only after testing resumes**:

```sh
cmake --preset dev
cmake --build --preset dev --parallel 2
ctest --preset dev --output-on-failure
cmake --preset release
cmake --build --preset release --parallel 2
ctest --preset release --output-on-failure
ctest --preset dev -R 'luca_(package_consumer|parent_consumer|package_options)_test' --output-on-failure -V
```

These include the authored relocation, alias/conflict/reconfiguration checks and
walkthrough runtime case. Cross-compiler CI and native MSVC support remain separate
pending items; authoring a job does not prove it works. No package-manager recipe,
release publication or repository rename was attempted.
