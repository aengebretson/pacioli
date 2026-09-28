"""Run an exploratory expiry forecast against an explicitly saved calendar."""
import argparse
import json
from pathlib import Path
import sys

from .calendar_cli import load_calendar
from .expiry_forecast import run_expiry_forecast


def read_document(path: Path) -> dict:
    if path.stat().st_size > 2*1024*1024:
        raise ValueError('Research input exceeds 2 MiB limit')
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('calendar', 'request', 'input', 'output'):
        parser.add_argument('--' + arg, type=Path, required=True)
    parser.add_argument('--expiration-id', required=True)
    parser.add_argument('--allow-rule-candidate', action='store_true')
    args = parser.parse_args()
    try:
        calendar = load_calendar(args.calendar)
        request = read_document(args.request)
        if request.get('research_use') != 'exploratory_historical':
            raise ValueError('Rule-derived expiration calendars currently support exploratory_historical runs only')
        cutoff = request['interval']['cutoff']
        resolved = calendar.forecast_interval(cutoff, args.expiration_id, allow_rule_candidate=args.allow_rule_candidate)
        if request['interval']['expiration'] != resolved['expiration']:
            raise ValueError('Requested expiration and selected calendar record disagree')
        request['interval'] = resolved
        result = run_expiry_forecast(request, read_document(args.input))
        bundle = {
            'schema_version': 'luca.calendar-forecast-run.v1',
            'calendar_reference': calendar.reference(),
            'expiration': calendar.expiration(args.expiration_id),
            'resolved_request': request, 'forecast': result,
        }
        with args.output.open('x') as handle:
            json.dump(bundle, handle, indent=2, allow_nan=False)
            handle.write('\n')
        print(json.dumps({'status': result['status'], 'output': str(args.output),
                          'calendar_sha256': calendar.sha256, 'sessions': len(resolved['interval_end_dates'])}))
        return 0 if result['status'] == 'complete' else 2
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
