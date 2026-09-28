# SPX reference calendar

Research now resolves forecast horizons from a saved, versioned calendar instead
of hand-entered session lists or downloaded PDF calendars. The same snapshot can
be passed to multiple research jobs. No web access occurs while building or
querying snapshots or running forecasts; installing the optional builder's
dependencies is a separate environment setup step.

## Contents and boundaries

- Cash-index sessions, holidays (absent sessions), early closes and UTC open/close
  timestamps, with America/New_York daylight-saving adjustments already resolved.
- Separate SPX AM monthly and SPXW PM date records. PM endpoints use the actual
  cash-session close, including 13:00 ET early closes. AM records retain the
  previous trading session and opening reference boundary. An AM SET publication
  time and exact historical last-trade time are not invented.
- Provider/rule versions, coverage limits and a SHA-256 content identity. Forecast
  requests retain that identity; old runs retain their original snapshot.

Expiration records are explicitly `rule_candidate`. They describe calendar
eligibility, not a historical listing of a particular strike or contract. PM
eligibility is modeled from 2023 onward, after weekday expirations were added;
earlier launch regimes are not extrapolated. Weekly/monthly/EOM series labels
must come from a qualified contract source. Both AM and PM dates may coexist.
Unknown dates and out-of-coverage queries fail rather than rolling silently.

The cash calendar is exchange_calendars XNYS, **not** Cboe's extended trading
calendar. Its maintained holiday rules include extraordinary closures. A snapshot
created today includes closures announced after some historical forecast origins;
it is not a historical announcement-vintage database. The wrapper therefore
accepts exploratory research only. Future dates remain subject to later notices.

## Build and use

The standard library and existing numerical dependencies do not provide a
maintained historical market calendar. The optional Apache-2.0-licensed
`exchange-calendars==4.13.2` supplies cash sessions; all extra dependencies are
pinned separately in `research/calendar-requirements.lock`. They stay outside the
C++ ledger and are needed only to build snapshots. Existing numerical pins are
unchanged. The reader uses standard-library code and explicit input data.

```sh
python -m pip install -r research/calendar-requirements.lock
export PYTHONPATH=research/src
python -m luca_research.calendar_cli build \
  --start 2005-01-01 --end 2027-12-31 --output /data/spx-calendar-v1.json
python -m luca_research.calendar_cli expirations \
  --calendar /data/spx-calendar-v1.json --start 2024-01-01 --end 2024-02-29 --root SPXW
python -m luca_research.calendar_cli interval \
  --calendar /data/spx-calendar-v1.json --cutoff 2024-01-03 \
  --expiration-id SPXW:PM:2024-02-02 --allow-rule-candidate
python -m luca_research.calendar_forecast \
  --calendar /data/spx-calendar-v1.json --request /data/request.json \
  --input /data/input.json --expiration-id SPXW:PM:2024-02-02 \
  --allow-rule-candidate --output /data/calendar-forecast.json
```

The forecast wrapper replaces the request's manually supplied interval list with
the stored calendar interval, verifies that the requested expiration agrees,
and saves the resolved request, calendar reference, expiration record and full
model result. It refuses AM settlement because the current forecast model ends
at a daily close. A session ending early remains one daily return interval;
intraday and partial-session variance allocation are not supported.

For callable use, pass a decoded snapshot to
`ExpirationCalendar(document).forecast_interval(cutoff, expiration_id,
allow_rule_candidate=True)`. Inject the returned interval into
`run_expiry_forecast`; financial calculations perform no hidden I/O.

## Maintenance and remaining integration

Keep snapshots in managed reference-data storage outside Git. Build a new file
when extending coverage or changing provider/rule versions; the builder refuses
to overwrite an existing snapshot. Select the new snapshot explicitly in new
runs, retain the old file, and review changes in session boundaries. Jobs can
reuse the stored snapshot offline; no PDF retrieval is required. Scheduled
refresh is not enabled by this implementation, consistent with paused automation.

The contract-data adapter must subsequently reconcile reference dates against
vendor/exchange contract metadata with root, settlement, listing availability,
source and timestamps. It must not promote a generic `SPX` vendor symbol into
verified AM or PM settlement by assumption. This version cannot authorize trades
or certify point-in-time listings. Platform HTTP/UI exposure and a historical
calendar-notice feed are separate integration work.

Sources: [Cboe SPX specifications](https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications),
[Cboe Weeklys specifications](https://www.cboe.com/tradable_products/sp_500/spx_weekly_options/specifications),
[exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).
