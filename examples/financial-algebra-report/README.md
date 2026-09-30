# Custom cash-report projection

An independent C++23 reporting projection using public LUCA financial algebras.
`cash_report.hpp` holds the pure application-owned projection; `main.cpp` supplies
bounded synthetic evidence and formats the result. Arithmetic and comparison
stay in `reduce_exact_cash` and `compare_exact_cash`.

Configure and compile from a source checkout without configuring the root build:

```sh
cmake -S examples/financial-algebra-report -B /tmp/luca-cash-report-build \
  -DLUCA_SOURCE_DIR="$PWD"
cmake --build /tmp/luca-cash-report-build --target luca-financial-algebra-report
```

For an installed LUCA containing `luca/financial_algebra.hpp`, omit
`LUCA_SOURCE_DIR` and supply `-DCMAKE_PREFIX_PATH=/path/to/luca/install`.
That mode links the public `luca::reconciliation` target. The standalone project
has no custom commands, test registration, root-build invocation or dependencies
beyond LUCA and the standard library. Current baseline exact arithmetic uses a
compiler with `__int128` support; strict ISO-pedantic-as-error builds reject that
existing implementation.

Execution is pending under the current test pause. Once authorized, run
`/tmp/luca-cash-report-build/luca-financial-algebra-report`. The intended output
identifies `example.cash-report@1`, a USD total of `800000000` at scale 6, a
`790000000` observation and an `amount_mismatch` difference of `-10000000`.
It prints policy/version, engine, recorded/economic/settlement cutoffs, each
projected source-event/source-record ID, and separate observation provenance.
These are intended acceptance values, not claimed runtime results.

The function groups by account and currency and preserves contribution order
inside a key. Empty input creates no implicit zero accounts. Exact matches keep
both evidence sides. Multiple currencies stay separate; observations remain
non-authoritative. The caller supplies already-valued contributions: no source
price, FX rate, lifecycle history or upstream policy is inferred. Law metadata
never authorizes regrouping, especially where intermediate fixed-width sums
could overflow. See [financial algebras](../../docs/financial-algebras.md).
