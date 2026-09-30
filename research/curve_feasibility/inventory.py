#!/usr/bin/env python3
"""Inventory only supplied local evidence; do not substitute unqualified data."""
import csv
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import re
import sys
from audit import digest, save, checkpoint

out=Path(sys.argv[1]).resolve()
ref=Path('/home/andrew/luca-development/state/maintenance/spx-trading-next-20260928/reference')
quotes=ref.parent/'event-reference/daily-quotes.csv'
old=Path('/home/andrew/vol-term-structure/data/replay-workers-20260928/qualify')
used=[]
contracts={}; errors=Counter()
p=ref/'daily/contracts.csv';used.append(p)
with p.open(newline='') as f:
    for row in csv.reader(f):
        if len(row)!=6: errors['contract_shape']+=1;continue
        key,vendor,symbol,expiry,strike,right=row
        match=re.fullmatch(r'(SPXW?)\s+(\d{6})([CP])(\d{8})',symbol)
        from decimal import Decimal
        if not match or match[2] != expiry.replace('-','')[2:] or match[3]!=right or Decimal(match[4])/1000!=Decimal(strike):errors['contract_symbol_mismatch']+=1
        if key in contracts and contracts[key]!=row:errors['contract_identity_conflict']+=1
        contracts[key]=row
counts=Counter({'rows':0,'replay_date_rows':0,'replay_date_target_expiry_rows':0}); dates=Counter();quality=Counter();groups=defaultdict(set);used.append(quotes)
with quotes.open(newline='') as f:
    for row in csv.reader(f):
        counts['rows']+=1
        if len(row)!=11:errors['quote_shape']+=1;continue
        dates[row[2]]+=1
        if row[1] not in contracts:errors['unknown_contract']+=1;continue
        c=contracts[row[1]]
        for flag in json.loads(row[8]):quality[flag]+=1
        if row[2]=='2026-09-25':counts['replay_date_rows']+=1
        if row[2]=='2026-09-25' and c[3]=='2026-10-23':counts['replay_date_target_expiry_rows']+=1
        groups[(row[2],c[3],c[4])].add(c[5])
ratep=old/'vendor-usd-rates-rows.json';used.append(ratep);rates=json.loads(ratep.read_text())
gzp=old/'vendor-usd-rates.csv.gz';used.append(gzp)
with gzip.open(gzp,'rt',newline='') as f:
    gr=list(csv.DictReader(f))
rate_status=json.loads((old/'pricing-input-status.json').read_text());used.append(old/'pricing-input-status.json')
hash_checks={a['path']:digest(old/a['path'])['sha256']==a['sha256'] for a in rate_status['usd_curve_acquisition']['artifacts']}
used += [old/a['path'] for a in rate_status['usd_curve_acquisition']['artifacts']]
sp=Path('/home/andrew/vol-term-structure/data/supporting-inputs-20260909/staged-v3.json');used.append(sp);staged=json.loads(sp.read_text())
public=staged['tables']['public_rate_observations']
cp=ref/'spx-calendar.json';used.append(cp);calendar=json.loads(cp.read_text())
idx=ref/'daily/index.csv';used.append(idx);idx_dates=Counter();idx_instruments=Counter()
with idx.open(newline='') as f:
    for r in csv.reader(f):
        if len(r)!=6:errors['index_shape']+=1;continue
        idx_dates[r[2]]+=1;idx_instruments[r[1]]+=1
result={'schema_version':1,'quote_schema':{'has_header':False,'columns':['dataset','instrument','date','bid','ask','vendor_iv','vendor_delta','quality_boolean_unqualified','quality_flags_json','source_hashes_json','row_hash'],'qualification':'11-column shape, contract-key join and OSI expiry/right/strike checked; inferred analytical columns and units not adopted for pricing. No time, timezone, bid/ask receipt, size or listing-vintage fields.'},
        'contract_count':len(contracts),'symbol_roots':dict(Counter(c[2].split()[0] for c in contracts.values())),
        'quote_counts':dict(counts),'quote_date_range':[min(dates),max(dates)],'quote_quality_flags':dict(quality),
        'date_expiry_strike_call_put_pairs':sum(v=={'C','P'} for v in groups.values()),'synchronized_intraday_pairs':0,'schema_errors':dict(errors),
        'rates':{'rows':len(rates),'gzip_rows':len(gr),'json_csv_semantic_match':all({k:str(v) for k,v in a.items()}=={k:str(v) for k,v in b.items()} for a,b in zip(rates,gr)) and len(rates)==len(gr),'dates':sorted({r['t_date'] for r in rates}),'period_range':[min(int(r['period']) for r in rates),max(int(r['period']) for r in rates)],'periods_contiguous':sorted(int(r['period']) for r in rates)==list(range(1,1801)),'original_hash_checks':hash_checks,'prior_date_vendor_rows':sum(r['t_date']<'2026-09-25' for r in rates)},
        'staged_public_rates':{'rows':len(public),'date_range':[min(r['observation_date'] for r in public),max(r['observation_date'] for r in public)],'series':sorted({r['series'] for r in public}),'tenors':sorted({r['tenor'] for r in public}),'publication_timestamps_present':sum(r['source_published_at_utc'] is not None for r in public),'discount_factors_present':sum(r['discount_factor'] is not None for r in public),'relevant_september_2026_rows':sum(r['observation_date'].startswith('2026-09') for r in public),'research_ready':staged['research_ready'],'missing_capabilities':staged['missing_capabilities']},
        'index_history':{'date_range':[min(idx_dates),max(idx_dates)],'instruments':dict(idx_instruments),'historical_publication_vintages_verified':False},
        'calendar':{'version':calendar['version'],'sessions':[s for s in calendar['sessions'] if s['date'] in ['2026-09-25','2026-10-23','2026-10-26']],'limitations':calendar['limitations']},
        'conclusion':'No supplied causal prior-date maturity discount or synchronized multi-strike September 25 target-expiry quotes. Daily pairs are date-level descriptive observations only.',
        'input_hashes':[digest(p) for p in sorted(set(used))]}
save(out/'evidence-inventory.json',result)
checkpoint(out,'Supplied rate and daily-option evidence inventoried; no causal substitutes adopted')
print(json.dumps({k:result[k] for k in ['quote_counts','quote_date_range','schema_errors','rates','staged_public_rates']},indent=2))
