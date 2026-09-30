"""Stream supplied local datasets; do not acquire data or copy licensed rows."""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from common import checkpoint, digest, existing_output, now, write_json

MAX_ROWS = 3000000


def summarize_csv(path, date_column, header=False, date_format='%Y-%m-%d'):
    count, widths, dates = 0, Counter(), []
    first, last = None, None
    with path.open(newline='') as stream:
        reader = csv.reader(stream)
        columns = next(reader) if header else None
        for row in reader:
            count += 1
            if count > MAX_ROWS:
                raise ValueError('inventory row bound exceeded')
            widths[len(row)] += 1
            d = datetime.strptime(row[date_column], date_format).date().isoformat()
            first, last = min(first or d, d), max(last or d, d)
    return {'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size,
            'rows': count, 'row_width_counts': dict(widths), 'columns': columns,
            'first_date': first, 'last_date': last}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--options', type=Path, required=True)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = existing_output(args.output)
    checkpoint(out, 'Streaming read-only inventory')
    result = {'schema_version': 'luca.curve-premium-inventory.v1', 'created_at': now(), 'datasets': []}
    result['datasets'].append(summarize_csv(args.reference / 'daily/index.csv', 2))
    contracts = {}
    symbols, rights = Counter(), Counter()
    cp = args.reference / 'daily/contracts.csv'
    with cp.open(newline='') as stream:
        for row in csv.reader(stream):
            if len(row) != 6 or row[0] in contracts:
                raise ValueError('conflicting or malformed contract identity')
            contracts[row[0]] = row
            symbols[row[2].split()[0]] += 1
            rights[row[5]] += 1
    result['datasets'].append({**summarize_csv(cp, 3), 'symbol_roots': dict(symbols), 'rights': dict(rights)})
    for path in sorted((args.reference / 'vix').glob('*_History.csv')):
        result['datasets'].append(summarize_csv(path, 0, True, '%m/%d/%Y'))
    flags, widths, by_year, rights = Counter(), Counter(), Counter(), Counter()
    n = unknown = crossed = bad_iv = 0
    first = last = None
    with args.options.open(newline='') as stream:
        for row in csv.reader(stream):
            n += 1
            if n > MAX_ROWS:
                raise ValueError('option inventory bound exceeded')
            widths[len(row)] += 1
            if len(row) != 11:
                raise ValueError('daily option export must have 11 headerless fields')
            d = row[2]
            datetime.strptime(d, '%Y-%m-%d')
            first, last = min(first or d, d), max(last or d, d)
            by_year[d[:4]] += 1
            if row[1] not in contracts:
                unknown += 1
            else:
                rights[contracts[row[1]][5]] += 1
            flags.update(json.loads(row[8]))
            crossed += float(row[3]) > float(row[4])
            bad_iv += not (0 < float(row[5]) < 10)
    result['datasets'].append({'path': str(args.options), 'sha256': digest(args.options),
        'bytes': args.options.stat().st_size, 'rows': n, 'row_width_counts': dict(widths),
        'first_date': first, 'last_date': last, 'rows_by_year': dict(by_year),
        'unknown_instrument_ids': unknown, 'rights': dict(rights), 'crossed_rows': crossed,
        'nonpositive_or_implausible_iv_rows': bad_iv, 'quality_flags': dict(flags),
        'inferred_headerless_schema': ['dataset_id', 'instrument_id', 'date', 'bid', 'ask', 'vendor_iv', 'vendor_delta', 'flag_boolean_unqualified', 'quality_flags_json', 'source_hashes_json', 'row_hash'],
        'eligible_exact_atm_rows': 0,
        'reason': 'All rows lack verified quote clock, historical settlement and vendor IV convention; no exact synchronized ATM study admitted.'})
    checkpoint(out, 'Daily option inventory complete', option_rows=n)
    feeds, exclusions, bounds = Counter(), Counter(), {}
    replay_path = args.replay / 'normalized-records.jsonl'
    with replay_path.open() as stream:
        for n, line in enumerate(stream, 1):
            if n > MAX_ROWS:
                raise ValueError('replay inventory bound exceeded')
            row = json.loads(line)
            feed, t = row['feed'], row['source_epoch_second']
            feeds[feed] += 1
            exclusions[str(row.get('exclusion'))] += 1
            lo, hi = bounds.get(feed, (t, t))
            bounds[feed] = (min(lo, t), max(hi, t))
    result['datasets'].append({'path': str(replay_path), 'sha256': digest(replay_path),
        'bytes': replay_path.stat().st_size, 'rows_by_feed': dict(feeds),
        'source_epoch_second_bounds': bounds, 'exclusions': dict(exclusions),
        'role': 'inventory only; single 2026 session cannot estimate historical normal premium; point-pricing gates remain failed'})
    evidence = []
    for name in ['REPORT.md','readiness.json','eligibility-policy.json','eligibility-results.json',
                 'pricing-input-status.json','existing-rate-evidence-check.json','manifest.json']:
        path = args.replay / name
        evidence.append({'path': str(path), 'sha256': digest(path)})
    result['qualification_evidence'] = evidence
    readiness = json.loads((args.replay / 'readiness.json').read_text())
    result['replay_qualification'] = readiness['quote_driven_replay']
    result['atm_gap'] = ['original observation/publication/receipt clocks', 'verified SPX versus SPXW identity and AM/PM fixing plus payment timestamp', 'same-strike same-expiry synchronized two-leg bid/ask, sizes and conditions', 'known-at-decision forward and discount with conventions', 'IV model, side, units and ATM selection rule', 'calendar/listing vintages; no daily-to-intraday relabeling']
    write_json(out / 'inventory.json', result)
    checkpoint(out, 'Inventory saved', datasets=len(result['datasets']))


if __name__ == '__main__':
    main()
