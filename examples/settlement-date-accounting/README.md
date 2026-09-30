# Side-by-side accounting projections

This standalone C++23 example uses the four immutable records and five evaluation
contexts from the existing accounting-foundations fixture. It displays the
trade-date and settlement-date journals, their evidence, portfolio quantities,
settled cash and open settlement obligations. Values are formatted from exact
scaled integers, without binary floating point.

`fixture.hpp` contains only synthetic input construction. The unit source reuses
it so example and test history stay aligned; financial calculations stay in the
public LUCA projection headers. Changing the fixture does not change the
independent expected amounts asserted in the unit source or portable JSON.

Compile from the repository root:

```sh
cmake -S examples/settlement-date-accounting -B /tmp/luca-settlement-date-example -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/luca-settlement-date-example --target luca_settlement_date_accounting -j2
```

This isolated CMake project has no test registration, custom build commands,
downloads or dependency on the root build. The existing installed-package
headers can also be used by linking a consumer to `luca::ledger` and
`luca::portfolio`.

After the execution pause is explicitly lifted, the executable can be run as
`/tmp/luca-settlement-date-example/luca_settlement_date_accounting`. It has not
been run as part of this worker assignment.

Expected policy comparison:

| Evaluation | Settlement-date entries | Accounting cash | Portfolio open obligation |
| --- | --- | --- | --- |
| Original purchase, June 2 knowledge | Contribution only | `100000.000000` | `5000.000000` payable |
| Corrected purchase, June 3 knowledge | Contribution only | `100000.000000` | `4400.000000` payable |
| Corrected purchase settled June 4 | Contribution + purchase | `95600.000000` | None |
| Reversal known, before June 6 settlement | Contribution + purchase | `95600.000000` | `4400.000000` receivable |
| Reversal settled June 6 | Contribution + purchase + reversal | `100000.000000` | None |

The trade-date policy recognizes unsettled securities and payable/receivable
controls. Settlement-date policy defers the equity journal until settlement.
Both consume the same lifecycle resolution at each explicit context. Neither
policy is a production chart or a GAAP/IFRS/tax/NAV implementation.
