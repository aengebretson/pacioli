# Checkpoint result cases

These authored synthetic fixtures specify expected financial state and evidence
for the additive state-plus-manifest continuation API. They are review inputs;
no checks have been executed under the current testing pause.

- `full-replay.json`: explicit 12-record cash/equity history, two-record
  checkpoint, exact final state, complete lifecycle/source lineage, selected
  active heads and watermark. It includes suffix-local correction, cancellation,
  reversal, multiple currencies and both settlement directions.
- `multiple-continuations.json`: extends that history by records 13 and 14,
  declares the exact state and evidence after each continuation, repeats a
  prefix source and removes zero EUR cash. Each request binds to the preceding
  returned manifest.
- `errors.json`: isolated variations of the named base case, with exact
  request/record changes and diagnostic alternatives. Includes all three
  prefix-targeting lifecycle actions, changed context/policy/hash, an empty
  suffix, economically early knowledge, intermediate overflow and two evidence
  construction errors.

`fixture_format` identifies this descriptive fixture envelope, not a new
financial wire schema. Amounts, quantities and prices are exact decimal
strings; dates and timestamps are explicit. A record's `payload` and
`provenance` fields map to existing public value factories; acceptance sequences
are assigned in listed order. In `errors.json`, `base_record_sequences`
selects records before applying a case's overrides; a case-specific selection
replaces the file-level selection. Rebuild the initial checkpoint from those
first two records after any prefix override. Request-only overrides do not
change that manifest or its digest.

Canonical expectations are relational: hash the existing LCB1 full ledger and
actual state, round-trip the resulting manifest, and compare repeated calls.
No unverified fixed digest vectors have been invented. Fixtures are mirrored
by the financial assertions in `tests/unit/checkpoint_result_test.cpp`; that
source also authors knowledge-cutoff, economic/source ordering, partition and
rich context-identity cases. The JSON documents currently have no machine
consumer; their correspondence to C++ remains an integration review item.
No Python financial calculator or new JSON dependency is introduced.

The directory deliberately has no generic `scenario.json`: the older portfolio
fixture harness does not understand lifecycle checkpoint-result envelopes.
Register the dedicated C++ target using the worker's `INTEGRATION.md`, then
execute it only after the user lifts the testing pause. Compilation alone
establishes neither full-replay equivalence nor runtime conformance.
