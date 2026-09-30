# O3 — Portable replay and checkpoint evidence

Status: coordinator-authored implementation design, 2026-09-30. Baseline: OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. Proposed work is additional to the integrated APIs; validation is not asserted.

## Outcome and baseline

A financial projection must be reproducible from the same immutable evidence, policy versions, and explicit evaluation context, regardless of execution host. Checkpoints accelerate the ordered financial fold only where the declared algebra permits safe continuation. They are derived state with evidence, not new authoritative events.

The baseline already implements LCB1 canonical bytes, SHA-256 digests, typed lifecycle encoding and decoding, portfolio-state encoding and decoding, a closed `CheckpointManifest`, and `CheckpointResumeRequest`. `check_checkpoint_resume_compatibility` validates the accepted prefix, state and manifest hashes, lineage, partition, context, and suffix shape. `apply_checkpoint_suffix` delegates to that check and then applies the selected suffix with existing portfolio engines. It preserves checked intermediate arithmetic and returns a new `PortfolioState`; it does not return a refreshed manifest or lineage.

Reuse is intentionally conservative: context is unchanged; the suffix is nonempty and contiguous; a correction, cancellation, or reversal targeting the prefix is rejected; economically earlier inputs are rejected. This is already useful functionality and must not be replaced with a broader but less evidenced cache.

## Bounded first-wave increment

Add an independent `luca/portfolio/checkpoint_result.hpp` with a proposed owned `CheckpointApplicationResult` and `apply_checkpoint_suffix_with_manifest` helper. Inputs mirror existing `apply_checkpoint_suffix`. Return the updated state together with a newly validated manifest describing the full accepted prefix plus compatible suffix. Preserve the existing state-only function unchanged.

Delegate financial computation and compatibility to existing public APIs. Reconstruct the complete accepted record sequence only to derive its canonical input digest and exact lifecycle evidence under the unchanged context; do not implement a second portfolio calculator. Rebuild the full-prefix count, final record, canonical state digest, context-selected active record lineage, source references, and resolved-event watermark from actual records. Never concatenate selected heads blindly: suffix-local corrections can supersede earlier suffix records. Preserve projection, engine, policy, partition, serialization, and context identities exactly.

Expose one complete result or a typed error preserving the original compatibility/application diagnostics, with an additional explicit construction failure only if needed. No caller input is mutated. Check arithmetic for sequence/count growth and use existing validating factories. If the existing v1 manifest cannot represent a legitimate result, return a documented diagnostic rather than inventing a watermark or changing wire semantics.

## Dependencies and reserved ownership

This additive work depends only on integrated lifecycle, serialization, portfolio, checkpoint factories, and suffix application. It can run beside accounting, algebra documentation/examples, and reconciliation. The replay worker owns the new header, a dedicated unit source, and a lane-specific implementation note. Root CMake and umbrella exports belong to the coordinator/package lane. Existing canonical schemas and shared headers remain unchanged unless a separate coordinated scope revision is necessary.

Advancing economic/knowledge/settlement cutoffs, prefix repairs after late corrections, empty checkpoints, partial-partition rebuilding, journal checkpoints, and durable storage remain later increments. The existing full replay is the fallback for incompatible knowledge; rejection is not permission to subtract a prior result.

## Acceptance and planned verification

An accepted ordinary suffix returns state equal to existing suffix application and a manifest whose input and state digests match canonical bytes. A second compatible continuation can use the refreshed bundle. Suffix-internal corrections retain complete history but only the correct active head. Prefix-targeting changes and altered policy/context still fail before result publication. Failure leaves every input unchanged.

Planned cases include continued replay versus full replay, canonical encode/decode of the refreshed manifest, invalid suffixes, late knowledge, overflow, and provenance ordering. These are verification requirements, not claimed results. Compilation is allowed; software tests and deployments remain paused by user instruction.
