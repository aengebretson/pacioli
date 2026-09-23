# Development workflow — protocol 2

Local protocol copy for Luca OSS. Canonical source: [Luca Platform development workflow](https://github.com/aengebretson/luca-platform/blob/main/docs/DEVELOPMENT_WORKFLOW.md). Paths under `planning/` refer to the canonical Platform planning worktree; the coordinator supplies a pinned OSS task and feature. Preserve financial rules in the local AGENTS.md.

## Source of truth

The product backlog is versioned in `planning/features/`. Features describe user outcomes, independently of agent sessions. `planning/tasks/` contains bounded assignments created by the coordinator. Existing B/A milestones retain their meaning; the roadmap maps new IDs to them. No historical acceptance evidence is upgraded merely by creating this backlog.

Luca Platform owns the combined roadmap. OSS implementation tasks name repository `oss`; reusable financial architecture, build instructions and conformance tests stay in the OSS repository. An OSS checkout receives a local copy of this protocol and AGENTS.md, version 2, with canonical-source attribution. An agent must not require access to the other repository to understand its assigned task.

Feature and task specifications may be revised through Git. Decisions and state changes are append-only journal events. `planning/STATUS.md` and `planning/COMPLETED.md`, when present, are generated views; they are never separate sources of truth.

## Responsibilities

The coordinator prioritizes features, checks readiness, decomposes work, resolves dependencies, reserves editing boundaries, dispatches workers and writes the shared journal. The implementation worker implements one assignment and produces a reviewable handoff. The integrator reviews and tests against current integrated code, merges sequentially and records evidence. These are roles; the same process may take different roles at different times, but an implementation claim cannot substitute for integration evidence.

Only the coordinator writes the journal and authoritative task transitions on its planning branch. Workers do not append to shared Markdown from their branches. Live process leases, inboxes, reports, PIDs, tmux pane IDs and raw logs live outside the tracked repository in a coordinator runtime directory. The journal references durable commits/artifacts; a tmux pane is never the only evidence.

## Assignment and isolation

1. Select a ready task with satisfied dependencies. Check for incompatible active file ownership; an allowed path ending in `/` is a directory prefix and overlaps its descendants; other paths are exact files. Wildcards are not supported. Shared interfaces and migration numbers need explicit coordination.
2. Create a dedicated branch and worktree from a recorded base commit. Assign one worker to it, record its task ID and configured model, and provide a report location.
3. Supply AGENTS.md, this pinned protocol, feature and task definitions directly in the launch brief. The worker acknowledges scope and checks before editing.
4. Run agents in named tmux sessions on stbridget. Use separate test ports, databases, container project names and finite CPU/memory budgets. Production services, credentials, data and container-engine access are not part of an ordinary feature assignment.
5. Deliver follow-up instructions through a documented agent resume/message mechanism or a task inbox consumed at checkpoints. Do not inject arbitrary text into a busy shell pane. Revised requirements create a revision event and are acknowledged before dependent work continues.
6. A worker reports progress, blocked prerequisites and review-ready results at checkpoints. Process exit is not proof of completion. Unexpected exits are recorded and reviewed before a bounded retry; never automatically relaunch indefinitely.

The coordinator may split a feature into tasks with different lanes (`api`, `editor`, `oss`, `reliability`). Lanes are scheduling labels, not independent product backlogs. Do not invent tasks solely to keep workers occupied. Blocked work can be reassigned only after preserving and identifying its commits and report.

## Handoff and integration

A worker writes `output/handoff.json` with exactly `status` (`review` or `blocked`), `summary` (string), `tests` (array of strings) and `limitations` (array of strings); see `planning/templates/handoff.json`. The summary identifies delivered criteria and changed behavior; tests include exact commands and actual results; limitations include unverified criteria, blockers and interface/schema/deployment impact. The coordinator adds task/feature IDs, base commit, changed paths and any resulting branch commit as assignment evidence. The combined handoff must identify a reviewable working-tree diff. No secret values or production customer data belong in the report. In the initial isolated-worker mode, workers do not commit or push: the common Git directory is mounted read-only. They leave changes and a handoff. The coordinator validates the diff and permitted paths, then commits and pushes the assigned feature branch for review. Never force-push shared history. A future change of worker permissions requires an explicit recorded operating-policy update.

The integrator checks scope, reviews the diff and evidence, incorporates the current target branch and runs checks appropriate to combined changes. Failures return the task to implementation or blocked with a reason. Merge one accepted branch at a time and record the resulting integration commit. Tests that require unavailable credentials, external login or infrastructure remain explicitly pending.

A task can be integrated while its feature remains open. Close the feature only when its end-to-end acceptance criteria pass. Deployment is a separate release step governed by the user's authorization and release runbook; this initial parallel development dispatch does not change production. Record deployment and public-site acceptance independently. Public Authentik acceptance, Safari and full-platform recovery remain pending until actually verified.

For paired OSS/platform work, land and identify the OSS commit or release first. The platform pins that dependency and runs compatibility tests. Do not silently consume a moving OSS branch or claim an atomic merge across repositories.

## Status and records

Task machine metadata is the first fenced JSON block: `id`, `feature`, `repository` (`platform` or `oss`), `state` (`ready` or `backlog` in the specification), `depends_on`, `lane` and `allowed_paths`. These are initial planning facts. Current status derives from coordinator events. A ready specification with an active assignment must not be dispatched twice. Resolve dependencies against verified integration/completion events, not process exit or stale task metadata.

Task transitions: backlog → ready → in_progress → review → integrated. Active tasks can become blocked; resuming requires an explicit ready/in_progress event and a resolved blocker. Features move through backlog → ready → in_progress → review → ready_to_release → released; features without deployment have `completed` only with recorded acceptance evidence. A correction references the earlier event; journal text is never rewritten to hide a failure.

See `planning/EVENT_FORMAT.md` and templates. Validate metadata and journal structure before dispatch and integration. Validation checks format and references; the coordinator still has to assess scope, dependencies and evidence. Changes to this protocol require a version bump, a recorded decision and explicit acknowledgement by active workers before new rules apply.

## Initial operating policy

Start independent API, editor and OSS assignments with a coordinator/integrator. Initial workers run in isolated containers with read-only common Git metadata; they cannot commit/push directly. The coordinator is the only process publishing their validated feature branches. Queue the reliability audit until capacity is available. The API worker owns gateway authentication paths; the editor consumes existing source-checkpoint endpoints and owns frontend paths; the OSS worker edits only OSS. Shared lockfiles, deployment manifests and infrastructure stay unassigned unless a reviewed dependency change needs them. Cap concurrency according to measured host/model capacity. Use provider credentials through configured agent tooling; never copy secrets into prompts or task files.

## Server coordination — protocol 2

The AI planning cycle and deterministic dispatcher run as separate systemd user services on stbridget. User lingering keeps them available without a desktop login. The planner wakes every 15 minutes, uses the configured server Codex credentials inside an isolated container, and proposes bounded tasks, promotions and advisory notes from the established roadmap. It has read-only inputs and cannot mutate source, canonical planning state, Git credentials, production services or the dispatcher.

Only the dispatcher validates and applies proposals under its existing exclusive writer lock. Task IDs, feature references, dependencies, ownership, scope and freshness are checked again at application time. No task-ID allowlist applies. Concurrency remains three implementation workers. New work must serve an established requirement; deferred features remain deferred. Invalid or stale proposals are retained as rejected evidence rather than silently expanding authority.

Worker completion still produces a branch for review. The server planner does not itself declare a feature accepted, merge code or deploy production. Requirements requiring user decisions are retained for the next conversation. Changes discussed here must be recorded in the canonical server planning files or inbox to be available when the laptop is offline. The desktop heartbeat is retired to prevent competing coordinators.

Existing assignments stay pinned to protocol 1 until they finish. Protocol 2 adds server-side planning for subsequent assignments without changing those workers' accepted scope. See [server coordinator operations](https://github.com/aengebretson/luca-platform/blob/main/docs/SERVER_DEVELOPMENT_COORDINATOR.md).
