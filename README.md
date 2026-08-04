# Pacioli

**Pacioli is an open-source financial data and accounting engine for trading systems.**

Pacioli provides a portable C++ core for representing, validating, transforming, and analyzing financial transactions, positions, portfolios, and ledgers. The same engine is intended to run in the browser through WebAssembly, in a local desktop service for private data, and in scalable hosted or customer-managed cloud environments.

## Project goals

- Define clear, deterministic financial semantics.
- Process columnar data efficiently with Arrow and Parquet adapters.
- Support local-first, private, self-hosted, and managed-service deployments.
- Expose one engine through native C++, CLI, service, WebAssembly, and language bindings.
- Keep datasets and calculations versioned, reproducible, and auditable.

## Repository structure

```text
apps/        User-facing applications: CLI, web, and eventually desktop
libs/        Portable C++ libraries and storage adapters
services/    Local daemon, API, and scalable worker hosts
tests/       Unit, integration, and cross-runtime conformance tests
bindings/    WebAssembly, C ABI, and future language bindings
packages/    Shared TypeScript clients, UI, and generated types
docs/        Architecture and contributor documentation
deploy/      Self-hosted and managed deployment assets
```

The repository is bootstrapped with `Pacioli::core`, the `pacioli` CLI, and the public Next.js website. Additional directories are added as their first working component lands rather than as empty placeholders.

## Build the C++ engine

Requirements:

- CMake 3.28 or newer
- Ninja
- A C++23 compiler (Clang, GCC, or MSVC)

```bash
cmake --preset dev
cmake --build --preset dev
ctest --preset dev
./build/dev/apps/cli/pacioli version
```

## Run the website

Requirements:

- Node.js 22
- pnpm 10

```bash
corepack enable
pnpm install
pnpm dev
```

## Deployment model

The public website is designed for Vercel. Public DNS can remain on Cloudflare, with the website hostname pointed to the Vercel project. Future Pacioli data planes may run locally, in customer-managed infrastructure, or as a managed service without changing the financial semantics in `Pacioli::core`.

See [docs/architecture.md](docs/architecture.md) and [docs/deployment.md](docs/deployment.md).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
