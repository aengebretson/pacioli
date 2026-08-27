# Slice 1 — LUCA identity and package

**Status:** Draft for implementation  
**Last updated:** 2026-08-27  
**Scope:** Open-source LUCA repository only

## Purpose

LUCA already contains a useful deterministic financial core: canonical cash and equity events, an ordered ledger, position/cash/settlement projections, reconciliation, conformance tests, and benchmarks. The next step is to turn that source tree into a coherent open-source C++ package that another application—especially LUCA Enterprise—can consume through a small, stable public boundary.

This slice changes project identity, build structure, packaging, examples, and CI. It must not change financial semantics.

## Decision summary

1. **The canonical project and library name is LUCA.**
2. **The canonical C++ namespace remains `luca`.**
3. **The CMake package name is `Luca`.**
4. **Public CMake targets are namespaced by domain:**
   - `luca::ledger`
   - `luca::portfolio`
   - `luca::reconciliation`
   - `luca::luca` as an optional umbrella target
5. **LUCA supports both source-tree and installed-package consumption:**
   - `add_subdirectory(...)`
   - `find_package(Luca CONFIG REQUIRED)`
6. **Nested consumers do not build LUCA tests, examples, or benchmarks unless explicitly requested.**
7. **The current GitHub repository should be renamed from `pacioli` to `luca` after the code and documentation consistently use the LUCA identity.**
8. **Because no stable release has been published, Slice 1 does not establish a permanent Pacioli compatibility API.** The existing `pacioli` forwarding surface should be removed unless a real external consumer is identified before implementation.

## Goals

- Establish one unambiguous public identity across repository, CMake, headers, options, documentation, and releases.
- Provide domain-oriented CMake targets that remain usable if implementation moves from header-only to compiled libraries later.
- Make LUCA safe to embed as a pinned dependency in LUCA Enterprise without polluting the parent build.
- Make LUCA installable to a prefix and discoverable with `find_package`.
- Prove the package with an external consumer test rather than testing only inside the LUCA source tree.
- Provide one concise end-to-end example that demonstrates the library’s actual financial value.
- Establish a cross-platform CI baseline before the API expands.
- Prepare a reproducible preview release.

## Non-goals

This slice does not add or redesign:

- economic-event semantics;
- cancellation, correction, reversal, or supersession;
- serialization or persistence;
- snapshots or incremental replay;
- journal/accounting projections;
- Python, C, REST, or gRPC bindings;
- package-manager publication through Conan, vcpkg, Homebrew, or system repositories;
- dynamic/shared-library ABI guarantees;
- adapters, services, databases, cloud infrastructure, or Enterprise workflows.

## Public target model

The source-tree targets should have non-namespaced implementation names and canonical aliases:

```cmake
add_library(luca_ledger INTERFACE)
add_library(luca::ledger ALIAS luca_ledger)
set_target_properties(luca_ledger PROPERTIES EXPORT_NAME ledger)

add_library(luca_portfolio INTERFACE)
add_library(luca::portfolio ALIAS luca_portfolio)
set_target_properties(luca_portfolio PROPERTIES EXPORT_NAME portfolio)
target_link_libraries(luca_portfolio INTERFACE luca::ledger)

add_library(luca_reconciliation INTERFACE)
add_library(luca::reconciliation ALIAS luca_reconciliation)
set_target_properties(luca_reconciliation PROPERTIES EXPORT_NAME reconciliation)
target_link_libraries(luca_reconciliation INTERFACE luca::portfolio)

add_library(luca INTERFACE)
add_library(luca::luca ALIAS luca)
set_target_properties(luca PROPERTIES EXPORT_NAME luca)
target_link_libraries(
  luca
  INTERFACE
    luca::ledger
    luca::portfolio
    luca::reconciliation)
```

The installed export should reproduce the same public names:

```text
Luca::ledger         — not desired
luca::ledger         — canonical
luca::portfolio      — canonical
luca::reconciliation — canonical
luca::luca           — canonical umbrella
```

CMake’s export namespace should therefore be `luca::`, while the package located by `find_package` remains `Luca`.

### Why domain targets instead of one target

The current implementation is header-only, but consumers should not need to change their build when modules later gain compiled implementation. Domain targets also keep dependency boundaries visible:

```text
ledger
  ↓
portfolio
  ↓
reconciliation
```

Future modules can extend the graph without making one monolithic target responsible for every dependency:

```text
accounting
adapters
serialization
```

## CMake behavior

### Project identity

The top-level project should become:

```cmake
project(luca VERSION 0.1.0 LANGUAGES CXX)
```

Canonical options should become:

```text
LUCA_BUILD_TESTS
LUCA_BUILD_EXAMPLES
LUCA_BUILD_BENCHMARKS
```

The old `PACIOLI_*` option names should be removed before the first preview release unless a concrete external compatibility need appears.

### Do not modify parent-project language policy

LUCA should express its C++ requirement on its public targets:

```cmake
target_compile_features(luca_ledger INTERFACE cxx_std_23)
```

It should not rely on globally setting `CMAKE_CXX_STANDARD` in a way that changes a parent project that embeds LUCA with `add_subdirectory`.

### Top-level-aware defaults

Tests and examples should default on only when LUCA is the top-level project. Benchmarks should remain explicitly opt-in.

Conceptually:

```cmake
set(LUCA_STANDALONE ${PROJECT_IS_TOP_LEVEL})
option(LUCA_BUILD_TESTS "Build LUCA tests" ${LUCA_STANDALONE})
option(LUCA_BUILD_EXAMPLES "Build LUCA examples" ${LUCA_STANDALONE})
option(LUCA_BUILD_BENCHMARKS "Build LUCA benchmarks" OFF)
```

When LUCA Enterprise uses:

```cmake
add_subdirectory(third_party/luca)
```

LUCA must contribute only its requested library targets by default. It must not unexpectedly enable testing, require Python, add benchmark executables, or modify global compiler settings.

### Build and install include paths

All public targets should use generator expressions:

```cmake
target_include_directories(
  luca_ledger
  INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/libs/ledger/include>
    $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
```

Equivalent declarations should apply to portfolio and reconciliation. No installed target may expose a source-tree path.

## Installed package design

Use standard CMake facilities:

- `GNUInstallDirs`
- `CMakePackageConfigHelpers`
- `install(TARGETS ... EXPORT LucaTargets)`
- `install(DIRECTORY ... DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})`
- `configure_package_config_file`
- `write_basic_package_version_file`

Expected install layout:

```text
<prefix>/
  include/
    luca/
      core.hpp
      core/...
      event.hpp
      ledger.hpp
      time.hpp
      portfolio.hpp
      portfolio/...
      reconciliation.hpp
      reconciliation/...
  lib/
    cmake/
      Luca/
        LucaConfig.cmake
        LucaConfigVersion.cmake
        LucaTargets.cmake
```

Expected consumer usage:

```cmake
find_package(Luca 0.1 CONFIG REQUIRED)

add_executable(example main.cpp)
target_link_libraries(example PRIVATE luca::portfolio)
```

## Header and identity cleanup

The canonical headers already live under `luca/...`; that should remain the only documented public include namespace.

The legacy forwarding header currently under `include/pacioli/` should be removed during this slice after checking for real external consumers. New examples, tests, Enterprise code, and documentation must not use the `pacioli` namespace or include prefix.

The implementation PR should search for and classify every remaining use of:

```text
Pacioli
pacioli
PACIOLI_
include/pacioli
```

References that describe project history may remain where useful. Build identifiers, API names, package names, and current documentation should use LUCA.

## Source-tree consumption by LUCA Enterprise

LUCA Enterprise is expected to pin an exact LUCA revision, initially through a submodule or equivalent source dependency, and consume only the public targets:

```cmake
add_subdirectory(third_party/luca)

target_link_libraries(
  luca-worker
  PRIVATE
    luca::portfolio
    luca::reconciliation)
```

Enterprise must not include internal LUCA source paths, copy LUCA implementation files, or depend on tests/benchmarks as if they were production APIs.

The same public target names must work in both source-tree and installed-package modes.

## End-to-end example

Add one example such as:

```text
examples/portfolio_replay.cpp
```

It should demonstrate a complete, intentionally small scenario:

1. create source/provenance identity;
2. deposit cash;
3. execute an equity purchase;
4. append events to a ledger;
5. project position state;
6. project settled cash and open settlement obligations;
7. reconcile against one deliberately incorrect observation;
8. print the resulting state and structured break.

The example is not a CLI product and must not introduce a JSON dependency. Its purpose is to show the public C++ API and prove that an external developer can understand the core workflow.

## External consumer test

Add a test project outside the normal LUCA target graph, for example:

```text
tests/package-consumer/
  CMakeLists.txt
  main.cpp
```

CI should:

1. configure and build LUCA;
2. install it into a temporary prefix;
3. configure the consumer with `CMAKE_PREFIX_PATH` pointing to that prefix;
4. build the consumer using only `find_package(Luca CONFIG REQUIRED)`;
5. execute the consumer and verify deterministic output.

This test is the release gate for packaging. Internal tests alone cannot prove that installed target metadata is correct.

## CI baseline

Slice 1 should establish at least:

- Linux with GCC;
- Linux with Clang;
- Windows with MSVC;
- Debug tests;
- Release tests;
- the install-and-consume test;
- one Linux AddressSanitizer/UndefinedBehaviorSanitizer job where supported;
- a benchmark executable smoke build with benchmarks enabled, without treating benchmark timing as a correctness assertion.

Financial-semantic conformance fixtures remain authoritative across configurations.

CI must build from a clean checkout without relying on developer-machine packages beyond documented build prerequisites.

## Repository rename and release posture

After the codebase, package, and documentation consistently use LUCA:

1. rename `aengebretson/pacioli` to `aengebretson/luca` in GitHub;
2. update local remotes and any Enterprise submodule URL to the canonical repository;
3. verify GitHub redirects from the old URL;
4. verify badges and documentation links;
5. tag a preview release such as `v0.1.0-preview.1` only after package-consumer CI passes.

The preview release is not an ABI guarantee. It establishes the first deliberate public package surface.

## Implementation plan

Slice 1 should be delivered through focused PRs rather than one large refactor.

### PR 1A — Canonical identity and modular targets

- rename the CMake project and options to LUCA;
- replace the single `pacioli` interface target with domain targets and aliases;
- express C++23 through target compile features;
- make tests/examples top-level-aware;
- remove or explicitly deprecate the Pacioli forwarding surface;
- preserve all existing tests and benchmark behavior;
- make no financial-semantic changes.

### PR 1B — Install and export package

- add install rules;
- generate `LucaConfig.cmake` and version metadata;
- export `luca::...` targets;
- add the external package-consumer test;
- verify clean-prefix installation.

### PR 1C — Example and CI matrix

- add the end-to-end portfolio replay example;
- add Linux GCC/Clang and Windows MSVC CI;
- add sanitizers where supported;
- build the optional benchmark target as a smoke check;
- document build, install, and consumption commands.

### Operational step 1D — Repository rename and preview release

- rename the GitHub repository to `luca`;
- update canonical URLs and Enterprise dependency references;
- publish `v0.1.0-preview.1` after all release gates pass.

## Acceptance criteria

Slice 1 is complete when all of the following are true:

- A clean source checkout builds and tests in Debug and Release.
- Linux GCC, Linux Clang, and Windows MSVC CI are green.
- LUCA can be embedded with `add_subdirectory` without building tests, examples, Python conformance tooling, or benchmarks by default.
- LUCA can be installed to an arbitrary prefix.
- A separate project can use `find_package(Luca CONFIG REQUIRED)` and link `luca::ledger`, `luca::portfolio`, and `luca::reconciliation`.
- Installed target metadata contains no source-tree include paths.
- The end-to-end example compiles and demonstrates ledger, projections, and reconciliation through public headers only.
- The public namespace, include paths, CMake targets, options, package name, documentation, and repository name consistently identify the project as LUCA.
- Existing unit, conformance, and benchmark behavior remains unchanged.
- No accounting, event-lifecycle, serialization, persistence, or distributed-system semantics are introduced.
- LUCA Enterprise has a documented, tested path to consume a pinned LUCA revision through public targets.

## Risks and mitigations

### Parent-build pollution

**Risk:** LUCA changes global compiler/test settings when embedded.  
**Mitigation:** target-level compile features, top-level-aware options, and a dedicated `add_subdirectory` consumer test.

### Incorrect installed metadata

**Risk:** the package works only in the source tree.  
**Mitigation:** install to a clean temporary prefix and build a separate consumer in CI.

### Identity breakage

**Risk:** old repository links or Pacioli names continue to circulate.  
**Mitigation:** perform the repository rename only after code consistency, rely on GitHub redirects, and document the transition in release notes.

### Premature compatibility burden

**Risk:** retaining duplicate Pacioli and LUCA APIs makes the public surface confusing indefinitely.  
**Mitigation:** remove the forwarding API before the first preview release unless a concrete external consumer is found.

### Oversized packaging slice

**Risk:** naming, packaging, CI, examples, and release work become one difficult PR.  
**Mitigation:** use PRs 1A–1C with independent acceptance criteria and no financial-semantic changes.

## Deferred decisions

The following decisions are explicitly deferred until there is a real consumer need:

- binary/shared-library distribution and ABI stability;
- package-manager publication;
- a C ABI;
- Python bindings;
- a command-line application;
- JSON or other canonical serialization;
- dynamic plugins;
- REST/gRPC hosts;
- precompiled binary releases.

## Exit condition

At the end of Slice 1, LUCA should feel like a deliberate open-source dependency rather than a source repository that happens to compile. An unfamiliar C++ developer should be able to clone or install it, build one example, link a domain target, and understand how LUCA’s ledger produces deterministic portfolio state.