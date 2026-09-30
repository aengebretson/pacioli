#!/usr/bin/env python3
"""Optional public-document snapshots only. No market data APIs or authentication."""
from pathlib import Path
import sys
import urllib.request
from audit import digest, save, utc
DOCS = {
 'iv-api.json':'https://raw.githubusercontent.com/IVolatility-com/API-docs/main/rest-api-ivlive-dev_formatted.json',
 'iv-intraday.pdf':'https://www.ivolatility.com/doc/Intraday%20data%20guide.pdf',
 'iv-trades.pdf':'https://www.ivolatility.com/doc/Intraday_options_trades_data_guide.pdf',
 'cboe-spx.pdf':'https://cdn.cboe.com/resources/spx/spx-fact-sheet.pdf',
 'occ-rules.pdf':'https://www.theocc.com/getcontentasset/9d3854cd-b782-450f-bcf7-33169b0576ce/dfc3d011-8f63-43f6-9ed8-4b444333a1d0/occ_rules.pdf',
 'occ-2026-holidays.pdf':'https://infomemo.theocc.com/infomemos?number=57897',
 'nyfed-reference.html':'https://www.newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates'
}
out=Path(sys.argv[1]).resolve(); docs=out/'public-documents';docs.mkdir(exist_ok=True)
results=[]
for filename,url in DOCS.items():
    p=docs/filename
    item={'url':url,'accessed_at':utc(),'purpose':'Public primary methodology or contract documentation, not a market-data request'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Q2-T17-local-documentation-audit/1.0'}),timeout=20) as r:
            b=r.read(12*1024*1024+1)
            if len(b)>12*1024*1024:raise ValueError('Public-document size cap')
            p.write_bytes(b)
            item.update(digest(p));item['content_type']=r.headers.get('Content-Type')
    except Exception as e:
        item['capture_error']=type(e).__name__+': '+str(e)
    results.append(item)
    save(out/'public-document-captures.json',results)
    print(filename, 'saved' if 'sha256' in item else item['capture_error'],flush=True)
