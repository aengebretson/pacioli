# LUCA conformance fixtures

This directory defines executable financial behavior independently of LUCA's
event, ledger, and projection implementations. Each scenario directory contains
machine-readable inputs in `scenario.json` and small, projection-specific
expected-state JSON files. Authoritative quantities and monetary amounts are
decimal strings; timestamps and dates use ISO 8601 text.

`scenario.json` identifies the scenario, supplies initial state and financial
inputs, and maps named lifecycle phases to expected position, cash, and
settlement files. Expected files use these shapes:

- `{"as_of": ..., "positions": [...]}`
- `{"as_of_date": ..., "cash": [...]}`
- `{"as_of": ..., "settlements": [...]}`

Each expected-state file has exactly one temporal anchor: `as_of` for an
expectation at a timestamp with a timezone, or `as_of_date` for an expectation
at date granularity. Settlement-date expectations use `as_of_date` and do not
imply a settlement time, timezone, or market-calendar rule.

The initial cases assume that equity positions change on trade date, while
settled cash moves only on settlement. A buy creates a payable and a sell creates
a receivable; settlement clears that obligation and updates settled cash.
Settlement dates are supplied, not calculated. Commissions, taxes, foreign
exchange, interest, corporate actions, and accounting policy are out of scope.

Input names such as `cash_deposit` and `equity_trade` are intentionally simple
conformance-fixture vocabulary. They do not define LUCA's future canonical
`EconomicEvent` schema. Production event names and representations may differ,
provided an implementation can consume the fixture semantics and produce the
specified expected state.

`harness.py` discovers scenario directories, loads every referenced file, and
validates their implementation-neutral structure. Future projection tests should
call `discover_scenarios()` or `load_scenario()` and compare their results with
the returned expected projections. They should not translate fixture fields into
assumptions about C++ class names, memory layout, storage, or replay machinery.

Run the validator through CTest (`ctest --preset dev`) or directly with:

```bash
python3 -m unittest discover -s tests/conformance -p 'test_*.py'
```
