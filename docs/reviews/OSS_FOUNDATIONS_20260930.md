# Financial algebras and projections: integration review

## Scope

Source baseline: `20e46a6a0c0744f9591968709adb0eb66aa5a411`.
Design seed: `08cbc3797b4ab34dc3adbb8a7c2fd30ea29b11ad`.
Reviewed O1-T04 packaging, O3-T11 checkpoint continuation, O4-T04 settlement-date
journals, O5-T06 financial algebra declarations/report projection, and F1-T01 exact
trade reconciliation/CSV observations. Each implementation is a separate commit,
followed by shared build integration and review corrections.

Three scoped static reviews covered replay/accounting, trade comparison/CSV,
and package/algebra contracts. No blocking financial implementation defect was
identified within those scopes. Static review does not establish runtime
correctness or completion of the broader roadmap.

## Integration and review corrections

- Registered all five focused semantic targets in the root build. Assertions remain
  active in Release as well as Debug.
- Exported and installed opt-in `luca::adapters`, linked to reconciliation, without
  widening the existing core/umbrella dependency graph.
- Added installed and embedded consumer coverage for new public headers and the CSV
  adapter. There are nine installed and eight embedded executable targets,
  including existing compatibility checks.
- Clarified checkpoint ordering as `(effective_at, acceptance_sequence)`: equal
  effective times are valid when acceptance sequence advances.
- Added authored checks for equal-time and multi-account/multi-currency checkpoint
  continuation, retaining existing tests and fixtures.
- Updated architecture, accounting, replay, algebra and roadmap documentation to
  distinguish implemented narrow interfaces from future capability groups.

## Compilation evidence

On 2026-09-30, the isolated worker image with GCC 12.2 and CMake 3.25.1 completed
13 configure/build/install steps, all with exit status zero:

1. Root Debug configuration and compilation of the five new semantic targets.
2. Root Release configuration and compilation of the same targets.
3. Installation followed by relocation to a different prefix.
4. Installed-package configuration and compilation of all consumers.
5. Embedded `add_subdirectory` configuration and compilation of all consumers.
6. Installed-package configuration and compilation of the financial-algebra report
   example and the package walkthrough.

Root configurations used C++23 target requirements and `-Wall -Wextra -Werror`.
Only the five new root targets were selected; the conformance generator target
was not built. Installed and embedded build projects were inspected for execution
side effects. No produced binary was run. `git diff --check` also passed.

## Pending acceptance and limitations

The standing user pause on automated software-test execution remains in effect.
No CTest, unit executable, conformance script, example executable, benchmark or
CI workflow was run. The compiler workflow is manual-only and defaults disabled.
Runtime validation remains pending. Compilation alone is not release approval.

After testing resumes, run the five new focused suites, existing replay/lifecycle/
journal/exact-cash checks, package option matrix, installed/embedded consumers,
and required full Debug/Release conformance. Some JSON expectation files are
only declarative; focused C++ suites encode principal cases, and the CSV suite
reads its eight raw fixtures. Do not claim a generic runner validates these JSON
expectations.

Accounting remains a narrow USD contribution/purchase/exact-reversal fixture
policy. Checkpoint continuation keeps unchanged cutoffs and rejects lifecycle
changes targeting the old prefix. Algebra declarations are metadata, not proofs
or permission for arbitrary regrouping. CSV source hashes and statement coverage
remain caller-supplied evidence. No live custodian/platform acceptance,
production accounting-standard coverage or deployment is claimed.

Clang remains unverified. Native MSVC remains blocked by baseline exact
arithmetic's `__int128` requirement; no weakened numeric substitute was introduced.


## Merge review — 2026-09-30

The user explicitly requested review and merge while the existing test-execution
pause remained in force. The PR head and base were unchanged from the reviewed
code, and GitHub had no submitted reviews, inline threads, discussion comments,
commit statuses or workflow runs. No merge conflicts were reported. A final
whole-branch whitespace review found and removed two trailing spaces in design
documents; financial source and build configuration were unchanged. The full
branch whitespace check then passed. Runtime test acceptance remains pending;
merge authorization does not convert compilation evidence into executed tests.
