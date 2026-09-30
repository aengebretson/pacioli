# External LUCA package walkthrough

This standalone CMake project uses only `find_package(Luca 0.1 CONFIG REQUIRED)`
and `luca::reconciliation` (which supplies portfolio and ledger transitively).
It contains synthetic inputs and presentation code; financial calculations stay
in the existing public library APIs. It can be copied outside the repository
with its `CMakeLists.txt` and `main.cpp`.

Build/install LUCA from the repository root, then build the consumer:

```sh
cmake -S . -B build/package -DLUCA_BUILD_TESTS=OFF -DLUCA_BUILD_TOOLS=OFF -DLUCA_BUILD_BENCHMARKS=OFF
cmake --install build/package --prefix /absolute/path/to/luca-install
cmake -S examples/package-consumer -B build/walkthrough -DCMAKE_PREFIX_PATH=/absolute/path/to/luca-install
cmake --build build/walkthrough --parallel 2
```

CMake 3.24+, C++23 `std::expected` and signed `__int128` support are required.
GCC 12.2 compilation was performed; runtime verification and Clang/Windows CI
were not. Native MSVC currently cannot compile the required exact arithmetic.
For multi-configuration generators, add `--config Release` to build/install.

After the automated-testing pause is lifted, run `build/walkthrough/luca_package_walkthrough`
(or the generator's configuration-specific executable path). Intended output,
**not a captured execution result**:

```text
position_scaled=1000000000 cash_before_scaled=1000000000 payable_before_scaled=200000000 cash_scaled=800000000 open_after=0
cash_break=amount_mismatch difference_scaled=-10000000 currency=USD observation_source=observation.bank.1
event=deposit-1 source=source.deposit.1
event=trade-1 source=source.trade.1
```

The explicit inputs are USD 1,000 deposited on June 4, 2026 and a purchase of
10 units at USD 20, settling June 5. `project_positions` reports 10 units.
`project_cash` and `project_settlement_obligations` derive two reporting views
from the same ordered ledger: before settlement, cash is USD 1,000 and the
payable is USD 200; after settlement, cash is USD 800 and no obligation is open.
Economic selection and settlement date are separate explicit context fields.
Money uses six decimal places; quantity uses eight. No binary floating-point
conversion is involved. This price times quantity requires no rounding; the
existing projection's valuation rule remains half-even when rounding is needed.

The independent bank observation says USD 790. `reconcile_cash` returns an
`amount_mismatch` with **observed minus expected = USD -10**. It preserves the
observation's provenance. The example separately prints the ledger event/source
identities retained as authoritative evidence; the existing simple cash balance
API does not itself carry a new per-balance lineage manifest. It never rewrites
ledger events to agree with the bank.

These are financial algebras and projections for reporting: domains and units
are explicit, exact additions are checked, and the ledger defines replay order.
Identity/associativity claims for exact addition require compatible keys and
representable intermediate results; fixed-width overflow can make reordered
computations differ in whether they succeed. Do not infer universal
commutativity, inverses or partition independence for lifecycle/accounting
operations from this example. No new generic algebra API or accounting policy
is introduced here.

The program is an execution host for library calls and console output. It has
no provider, database, service or hidden financial I/O. It demonstrates a narrow
cash/equity case, not lots, NAV, tax, GAAP/IFRS completeness or new lifecycle
semantics. The installed-consumer suite contains a pending deterministic-output
acceptance case for this same source.
