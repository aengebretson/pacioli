# Contributing to Pacioli

Pacioli is early-stage and architecture-sensitive. Contributions should preserve deterministic financial semantics, explicit data contracts, and portability across local and hosted runtimes.

## Development workflow

1. Create a focused branch.
2. Build and test the native project with CMake presets.
3. Typecheck and build the web project with pnpm.
4. Add tests for behavior changes.
5. Open a pull request explaining the problem, the chosen boundary, and any compatibility implications.

```bash
cmake --preset dev
cmake --build --preset dev
ctest --preset dev

corepack enable
pnpm install
pnpm typecheck
pnpm build:web
```

## Design principles

- Keep financial-domain logic out of UI and infrastructure layers.
- Prefer immutable, versioned inputs and deterministic outputs.
- Avoid global CMake configuration; model dependencies on targets.
- Keep large tabular data columnar rather than converting it to object-per-row JSON.
- Add dependencies only when they solve a current, demonstrated requirement.
- Do not log confidential financial records or values by default.

## Commit and pull request scope

Keep changes reviewable and use conventional commit-style subjects where practical, such as `feat(core):`, `fix(web):`, `test:`, `docs:`, and `build:`.
