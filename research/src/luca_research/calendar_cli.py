"""Build reference data explicitly; query saved snapshots without downloads."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from importlib.metadata import version
import json
from pathlib import Path
import sys

from .expiration_calendar import ExpirationCalendar, MAX_DAYS, SCHEMA, content_hash, iso_date


def build_snapshot(start: str, end: str) -> dict:
    """Optional upstream calendar dependency is used only when refreshing."""
    left, right = iso_date(start), iso_date(end)
    if left < date(2005, 1, 1) or not 0 < (right-left).days < MAX_DAYS or right < date(2023, 1, 1):
        raise ValueError('Use coverage starting in 2005 or later, ending in 2023 or later, under 12000 days')
    import exchange_calendars as calendars
    from zoneinfo import ZoneInfo
    # Include the previous session for AM candidates on the range boundary.
    calendar = calendars.get_calendar('XNYS', start=left-timedelta(days=14), end=right+timedelta(days=14))
    ny = ZoneInfo('America/New_York')
    sessions, expirations = [], []
    all_days = []
    for stamp, row in calendar.schedule.iterrows():
        day = stamp.date()
        all_days.append(day)
        if day < left or day > right:
            continue
        opening, closing = row['open'], row['close']
        record = {
            'date': day.isoformat(),
            'open_at': opening.isoformat().replace('+00:00', 'Z'),
            'close_at': closing.isoformat().replace('+00:00', 'Z'),
            'early_close': closing.tz_convert(ny).hour < 16,
        }
        sessions.append(record)
        if day >= date(2023, 1, 1):
            expirations.append({
                'expiration_id': 'SPXW:PM:' + day.isoformat(), 'root': 'SPXW',
                'date': day.isoformat(), 'settlement': 'PM', 'status': 'rule_candidate',
                'series_kind': 'PM_date_eligible_series_unqualified',
                'last_trading_session': day.isoformat(), 'last_trade_at': record['close_at'],
                'settlement_reference_at': record['close_at'],
                'contract_listing_verified': False,
            })
    # Standard AM date is the third Friday, moved to the preceding cash
    # session for an exchange holiday. Never conflate it with same-day PM.
    days_set = set(all_days)
    by_day = {r['date']: r for r in sessions}
    for year in range(max(left.year, 2023), right.year+1):
        for month in range(1, 13):
            first = date(year, month, 1)
            nominal = first + timedelta(days=(4-first.weekday()) % 7 + 14)
            if not left-timedelta(days=7) <= nominal <= right+timedelta(days=7):
                continue
            actual = nominal
            while actual not in days_set and actual >= left-timedelta(days=14):
                actual -= timedelta(days=1)
            if not left <= actual <= right or actual.isoformat() not in by_day:
                continue
            previous = max(d for d in all_days if d < actual)
            expirations.append({
                'expiration_id': 'SPX:AM:' + actual.isoformat(), 'root': 'SPX',
                'date': actual.isoformat(), 'nominal_date': nominal.isoformat(),
                'settlement': 'AM', 'status': 'rule_candidate', 'series_kind': 'standard_monthly',
                'last_trading_session': previous.isoformat(),
                'last_trade_at': None,
                'settlement_reference_at': by_day[actual.isoformat()]['open_at'],
                'settlement_reference_note': 'Cash-session opening boundary; not the SET publication time. Constituent opening prices determine settlement.',
                'contract_listing_verified': False,
            })
    doc = {
        'schema_version': SCHEMA, 'calendar_id': 'luca-spx-reference',
        'version': 'rules-v1-exchange-calendars-' + version('exchange-calendars'),
        'coverage': {'start': start, 'end': end},
        'expiration_rule_coverage': {'start': max(left, date(2023, 1, 1)).isoformat(), 'end': end},
        'timezone': 'America/New_York',
        'sources': {
            'cash_sessions': {'provider': 'exchange_calendars', 'version': version('exchange-calendars'), 'calendar': 'XNYS',
                              'url': 'https://github.com/gerrymanoim/exchange_calendars'},
            'product_rules': ['https://www.cboe.com/tradable-products/sp-500/spx-options/spx-specifications',
                              'https://www.cboe.com/tradable_products/sp_500/spx_weekly_options/specifications'],
            'installed_tzdata_version': version('tzdata'),
            'timezone_resolution': 'ZoneInfo uses host zoneinfo with the installed tzdata package as fallback; resolved UTC boundaries are frozen in this snapshot.',
        },
        'limitations': [
            'Cash-equity sessions for daily SPX variance; not Cboe global/curb trading hours.',
            'Expiration rows are rule candidates, not proof of a listed contract or its availability at a historical cutoff.',
            'PM date eligibility starts in 2023; earlier product launch/rule regimes are deliberately unsupported.',
            'AM opening boundary is not a guaranteed SET publication timestamp; exact AM last-trade timestamps require a versioned contract source.',
            'Schedule reflects this provider version, including subsequently announced closures; historical announcement vintages are not modeled.',
            'Future schedules can change; refresh explicitly and pin snapshots in analyses.',
        ],
        'sessions': sessions, 'expirations': sorted(expirations, key=lambda r: (r['date'], r['root'])),
    }
    doc['sha256'] = content_hash(doc)
    ExpirationCalendar(doc)
    return doc


def load_calendar(path: Path) -> ExpirationCalendar:
    if path.stat().st_size > 16*1024*1024:
        raise ValueError('Calendar exceeds 16 MiB limit')
    return ExpirationCalendar(json.loads(path.read_text()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--start', required=True)
    build.add_argument('--end', required=True)
    build.add_argument('--output', type=Path, required=True)
    for command in ('sessions', 'expirations', 'interval'):
        child = sub.add_parser(command)
        child.add_argument('--calendar', type=Path, required=True)
        if command == 'interval':
            child.add_argument('--cutoff', required=True)
            child.add_argument('--expiration-id', required=True)
            child.add_argument('--allow-rule-candidate', action='store_true')
        else:
            child.add_argument('--start', required=True)
            child.add_argument('--end', required=True)
            if command == 'expirations':
                child.add_argument('--root', choices=['SPX', 'SPXW'], default='SPXW')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            doc = build_snapshot(args.start, args.end)
            # Never silently replace a reference snapshot used by prior runs.
            with args.output.open('x') as handle:
                json.dump(doc, handle, indent=2, allow_nan=False)
                handle.write('\n')
            result = {'output': str(args.output), 'sha256': doc['sha256'], 'sessions': len(doc['sessions']), 'expirations': len(doc['expirations'])}
        else:
            cal = load_calendar(args.calendar)
            if args.command == 'interval':
                result = cal.forecast_interval(args.cutoff, args.expiration_id, allow_rule_candidate=args.allow_rule_candidate)
            elif args.command == 'sessions':
                result = cal.sessions(args.start, args.end)
            else:
                result = cal.expirations(args.start, args.end, args.root)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
