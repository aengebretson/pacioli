# Architecture

Pacioli is organized around one portable financial engine and several execution hosts.

## Layers

1. **Core libraries** contain deterministic financial models and calculations.
2. **Adapters** connect the core to Arrow, Parquet, databases, filesystems, and object storage.
3. **Execution hosts** expose the engine through WebAssembly, a local daemon, scalable workers, and APIs.
4. **Applications** provide the CLI, web interface, and desktop shell.

The UI is never the authoritative implementation of financial semantics.

## Planned runtime model

- **Browser:** C++ compiled to WebAssembly, running in a Web Worker for private local analysis.
- **Desktop:** one React UI packaged with a thin desktop shell and a supervised native `paciolid` sidecar.
- **Private service:** containerized API, workers, metadata database, and customer-controlled data storage.
- **Managed cloud:** the same stateless workers operating on versioned datasets through a durable job system.

## Scalable calculation contract

A managed calculation should be a deterministic, resource-bounded transformation from versioned input datasets to versioned output datasets. Workers remain stateless; durable services own job state, tenancy, storage, retries, and scheduling.

## Repository evolution

Directories are introduced with working code rather than empty placeholders. Near-term additions are expected to include:

- `libs/arrow` and `libs/parquet`
- `bindings/wasm`
- `services/application`, `services/api`, and `services/worker`
- `apps/desktop`
- `packages/api-client` and `packages/ui`
- cross-runtime conformance fixtures under `tests/conformance`
