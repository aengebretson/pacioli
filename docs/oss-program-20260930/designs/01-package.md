# O1 — Consumable LUCA package

## Outcome and baseline
Make LUCA a normal standalone C++23 dependency for financial algebras and reporting projections. Source baseline is stbridget OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. O1-T01–T03 already supply installed and parent-project consumers, relocatable exports, and `luca::ledger`, `luca::portfolio`, `luca::reconciliation`, `luca::luca`. Preserve those capabilities; this is completion work, not a bootstrap. The repository and root project still use Pacioli naming. Existing accounting headers are delivered through `luca::ledger`; splitting their package is a later compatible migration.

## First increment: O1-T04
Use LUCA as the CMake project identity and introduce canonical `LUCA_BUILD_TESTS`, `LUCA_BUILD_BENCHMARKS`, and `LUCA_BUILD_TOOLS` options. Preserve explicit existing `PACIOLI_*` option values as documented compatibility aliases. When both names are explicitly set incompatibly, fail with an actionable diagnostic rather than silently changing caller intent. Keep the existing `pacioli` source target and forwarding header compatible; do not rename the GitHub repository, publish a tag, or claim a new ABI guarantee.

Retain the public CMake target dependency graph and relative install metadata. Parent projects default to no LUCA tests, Python discovery, tools, or benchmarks unless requested. Provide a small external-consumer walkthrough of explicit input → public projection → exact reconciliation. Document financial algebra/projection terminology and the difference between the financial library and its execution hosts. Update the baseline audit to distinguish source changes, actual build evidence, and pending verification.

Author compiler CI definitions for Linux GCC/Clang and Windows MSVC where they can use the same public API and supported toolchain. An authored job is not evidence that the compiler works. Keep unavailable compiler behavior explicit. Maintain C++23 requirements and checked exact arithmetic; no numeric fallback or weakened checks to satisfy a platform.

## Ownership and dependencies
This lane alone edits root CMake, presets, package metadata, package/parent consumer projects, compatibility includes, CI definitions and packaging documentation. It uses only the pinned baseline. The other lanes add headers and isolated compile/test projects; their root registration and cross-lane integration happen later. No worker depends on this naming change before beginning its own implementation.

## Acceptance and verification
An installed consumer and an embedded consumer must expose the same four public target names and domain dependency graph. Exported package metadata must contain no absolute build/source path. Default parent configuration must avoid LUCA test/tool side effects. Existing legacy consumers must remain source-compatible, and contradictory option settings must have defined behavior. Standalone deterministic results must remain unchanged.

Necessary configure/build/package compilation is allowed. The standing user pause prohibits executing automated tests, CI and deployment in this batch. Author missing checks and list their exact later commands; do not execute consumer smoke programs or claim cross-platform acceptance. Integration will run the relevant package/consumer checks after testing resumes.

## Follow-up
After review and verification, coordinate repository rename, compatibility deprecation policy, release notes and preview tagging separately. The worker leaves a reviewable diff and handoff; it does not publish a release.
