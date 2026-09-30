# Standalone trade comparison projection

`main.cpp` supplies an explicit custodian ID mapping for a lifecycle-resolved
trade, parses original and corrected synthetic statements independently and
compares them with the corrected authoritative row. The hand-calculated outcome
is two differing fields (quantity/price), then an exact match; original and
corrected evidence remain separate. The example is authored and compiled, but
has not been executed during the standing test pause.

The independent project includes only ledger, reconciliation and adapter public
headers. It does not add the repository root, generate conformance artifacts,
register CTest, install files or run executables during builds.

From the repository root, compile only:

```sh
cmake -S examples/trade-reconciliation -B /tmp/luca-trade-build -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/luca-trade-build --target trade_reconciliation_example trade_reconciliation_test trade_csv_test -j 2
```

After the user explicitly resumes automated testing, the pending commands are:

```sh
/tmp/luca-trade-build/trade_reconciliation_test
/tmp/luca-trade-build/trade_csv_test
/tmp/luca-trade-build/trade_reconciliation_example
```

The CSV unit executable reads the eight fixture files from the source directory
specified at configure time; preserve that directory when eventually running it.
All source digests in this demonstration are explicitly synthetic labels, not
hash-verification or authenticity evidence. See `docs/trade-reconciliation.md`
for the API, domain, operation laws, limits and deferred integrations.
