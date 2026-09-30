# Exact trade comparison fixtures

`cases.json` is a portable, synthetic semantic fixture, not the baseline portfolio
`scenario.json` format or a canonical wire serialization. Each case selects its
explicit lifecycle records, mapping, CSV, statement identity and digest. Context
is shared exactly; statement timestamps do not stand in for knowledge cutoffs.
The correction replaces 100 shares at 50 with 80 at 55. The original statement
then differs in quantity and price; a separately identified corrected statement
matches. Matching numbers with a different external ID still produce two breaks.

Expected entries are sorted by account then external trade ID. A present
`projected_lineage` expands to the complete selected records/provenance above;
`observed_physical_row` expands to independently owned statement-row evidence,
including the supplied digest. Neither lineage branch replaces the other.

The focused unit sources encode these financial rules plus individual field
mismatches, signs, currencies, deterministic order, incompatible cutoffs, mapping
ambiguity, cancellation/reversal evidence, UTF-8, decimal and parser limits.
`trade_csv_test.cpp` also reads these eight CSV files when eventually executed.
A general JSON fixture runner is not introduced or registered in the shared
portfolio harness. Runtime verification of all authored checks is pending the
user lifting the testing pause; no fixture has been executed for this handoff.
