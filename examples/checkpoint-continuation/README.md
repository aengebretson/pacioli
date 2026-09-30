# Checkpoint continuation

This standalone C++23 consumer demonstrates a reporting projection over synthetic
USD cash evidence: 1000, then +100, then -25. Each continuation uses the returned
owned state and validated manifest to construct the next resume request. The
intended final cash is exactly 1075 USD with three accepted records.

Compile from the repository root (build directory may be outside the checkout):

```sh
cmake -S examples/checkpoint-continuation -B /tmp/luca-checkpoint-continuation
cmake --build /tmp/luca-checkpoint-continuation --target checkpoint_continuation checkpoint_result_compile -j2
```

The project uses only the existing ledger/portfolio include roots and the
standard library. It does not configure the root project, generate conformance
artifacts, register tests, or execute either binary. `checkpoint_result_compile`
compiles and links the authored unit checks; compilation is not runtime evidence.
Test and example execution remain pending under the current operating pause.

An installed consumer can instead include
`<luca/portfolio/checkpoint_result.hpp>` and link `luca::portfolio`. For the
contract, error alternatives, and ordered financial algebra preconditions see
[checkpoint-result.md](../../docs/checkpoint-result.md).
