# LUCA OSS designs and parallel workers

Prepared September 29, 2026 (Chicago), September 30 UTC. Source baseline: `20e46a6a0c0744f9591968709adb0eb66aa5a411`.

The framework remains **financial algebras and reporting projections**: immutable economic history, typed operations with explicit laws, and named/versioned report derivations with lineage. Source/observations remain separate. See the [shared implementation contract](CONTRACT.md).

## Design index

| Design | First-wave task |
|---|---|
| [O1 — Consumable LUCA package](designs/01-package.md) | O1-T04 |
| [O2 — Immutable lifecycle algebra and reporting projections](designs/02-lifecycle.md) | Later increment |
| [O3 — Portable replay and checkpoint evidence](designs/03-replay.md) | O3-T11 |
| [O4 — Accounting algebras and journal projections](designs/04-accounting.md) | O4-T04 |
| [O5 — Financial algebras and reporting projections](designs/05-algebras.md) | O5-T06 |
| [Portable execution — One financial algebra, multiple hosts](designs/06-portable-tools.md) | Later increment |
| [F1 — Trade comparison algebra and custodian observations](designs/07-reconciliation.md) | F1-T01 |
| [Roadmap item 8 — Corporate-action algebras and entitlement projections](designs/08-corporate-actions.md) | Later increment |
| [Roadmap item 9 — Portfolio-accounting algebras and reporting projections](designs/09-portfolio-accounting.md) | Later increment |
| [Roadmap item 10 — Securities-finance algebras and obligation projections](designs/10-securities-finance.md) | Later increment |
| [Roadmap item 11 — Scale and external representations of financial algebras](designs/11-scale-adapters.md) | Later increment |

## Parallel work

Five independent implementation streams: package, replay, accounting, algebra/reporting and trade reconciliation. Each uses a separate branch/worktree and 4 CPU / 8 GiB isolated worker, with a four-hour maximum. Shared build files have one owner. This is a manual bounded batch; existing automated-dispatch settings and sessions are preserved.

| Session | Task | Deliverable |
|---|---|---|
| `luca-oss-package` | O1-T04 | Finish LUCA package identity with compatibility |
| `luca-oss-replay` | O3-T11 | Return refreshed evidence with continued checkpoint state |
| `luca-oss-accounting` | O4-T04 | Add the settlement-date accounting projection |
| `luca-oss-algebra` | O5-T06 | Expose financial algebra contracts and custom report projection |
| `luca-oss-reconciliation` | F1-T01 | Implement exact trade comparison and CSV observation adapter |

Portable hosts and broader financial features follow after their prerequisites are reviewed. Five streams increase independent progress; they do not remove the need for sequential integration and later verification.

## Operating status

This index is a design/launch artifact, not evidence that implementation has finished. The dispatch receipt and startup evidence will identify actual launches and acknowledgements. Workers author focused tests but do not execute them under the user's standing testing pause. Necessary compilation is allowed. No deployment or release is part of this batch.

Canonical server planning: `/home/andrew/luca-development/control/planning/designs/oss-20260930/`.
Runtime: `/home/andrew/luca-development/state/maintenance/oss-20260930/`.
Each worker has `output/STATUS.md`, `output/INBOX.md`, and final handoff files. Use the exact worker conversation ID for continuation; never a shared resume-last command.
