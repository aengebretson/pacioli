# Portable execution — One financial algebra, multiple hosts

Status: coordinator-authored implementation design, 2026-09-30. Baseline: OSS commit `20e46a6a0c0744f9591968709adb0eb66aa5a411`. This is a sequenced follow-on feature, not a claim that general hosted parity already exists.

## Outcome and current implementation

A user should run the same versioned financial projection from C++, a command-line batch, Python, or a LUCA service and receive identical financial content for identical evidence, policies, and cutoffs. Hosts package an invocation and its output; they do not redefine the financial algebra.

The baseline build inventory and `docs/transformation-contract.md` document the `luca-exact-cash` standalone host and the source-importable `tools/exact-cash/python/luca_exact_cash` adapter. The closed `luca.exact-cash-cli.v1` request delegates to public exact-cash reduction and comparison. Python supervises the executable with explicit limits and validates the response; it is not a native binding or independent arithmetic implementation. This bounded path is useful evidence of the intended architecture, not a complete portfolio CLI. The supplied design snapshot includes its documented contract/build references rather than the complete tool sources; an implementation assignment must inspect those sources in its worktree before editing.

## Next deliverable and boundary

Add a separate versioned portfolio-projection host after the current packaging and accounting increments are reviewable. A proposed `luca-portfolio` command accepts explicit lifecycle input and a closed request describing recorded/economic/settlement cutoffs and the selected supported projection. It decodes canonical typed records through existing APIs, resolves lifecycle knowledge once, and calls existing portfolio or explicitly selected journal projections. Do not extend the existing exact-cash schema to smuggle in unrelated financial shapes.

Use strict decimal strings at human-facing JSON boundaries and canonical LCB1 bytes when an existing O3 type is transported. A JSON envelope is host framing, not a competing canonical financial format. New journal wire values require a separate versioned contract; until available, support the integrated portfolio-state format first. Required dependencies therefore vary by projection: portfolio execution can use current O2/O3; journal transport waits for its own schema and accounting implementation.

A result identifies the operation, engine, policy, exact evaluation context, input identities/digest, result format, and available projection evidence. A request must never claim more lineage than the underlying projection supplies. Host execution ID, duration, machine name, logs, and file paths belong in operational sidecars outside the financial digest. Unknown schemas, policies, incomplete evidence, and unsupported capabilities fail explicitly.

## Python and hosted parity

Keep the Python adapter thin: explicit executable path, bounded request/response size, timeout, structured error categories, and no executable discovery or hidden configuration. Share deterministic financial fixtures across invocation paths. A later platform adapter pins an OSS commit/release and invokes the same implementation; authorization, uploads, persistence, and scheduling remain platform responsibilities.

Parity compares canonical financial payload and evidence, excluding sidecar metadata. Matching formatted text alone is insufficient. No platform integration can depend on an unmerged moving branch while claiming release compatibility.

## Ownership and sequencing

Queue this lane behind package naming/export decisions to avoid overlapping root build and install changes. Its owned paths are a new tool directory, its Python adapter, dedicated fixture/CLI sources, and a tool guide. A coordinator owns shared build/export changes. The initial parallel wave can deliver accounting, checkpoint evidence, algebra declarations, and reconciliation without any portable-host code being available first.

## Acceptance and planned verification

Prepare one canonical lifecycle input covering contribution, purchase, correction, settlement, and reversal. Direct C++, standalone host, and Python must yield the same supported portfolio payload and structured failures. Check malformed input, size limits, timeouts, nonzero exits, stale versions, and decimals that would lose precision in binary floating point. Hosted parity remains pending until a separately pinned platform task runs it.

Compilation is allowed. Software tests and deployments remain paused under the user's standing instruction; none were executed for this design. Native Python bindings, package publication, remote job scheduling, and hosted rollout are explicitly later delivery work.
