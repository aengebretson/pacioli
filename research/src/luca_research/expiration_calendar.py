"""Offline, explicit-input SPX reference calendar for daily-close research.

Calendar construction and persistence live in calendar_cli. This module has
no filesystem/network access and does not establish historical option listings.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json

SCHEMA = 'luca.spx-expiration-calendar.v1'
MAX_DAYS = 12000


def content_hash(document: dict) -> str:
    payload = {k: v for k, v in document.items() if k != 'sha256'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def iso_date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Dates must use YYYY-MM-DD')
    return parsed


def utc_time(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError('Timestamps must be explicit UTC with Z suffix')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class ExpirationCalendar:
    """Validate and query a versioned, content-addressed reference snapshot."""

    def __init__(self, document: dict):
        if document.get('schema_version') != SCHEMA:
            raise ValueError('Unsupported calendar schema')
        if document.get('sha256') != content_hash(document):
            raise ValueError('Calendar content hash mismatch')
        self._document = deepcopy(document)
        self.sha256 = document['sha256']
        self.calendar_id = document['calendar_id']
        self.version = document['version']
        self.start = iso_date(document['coverage']['start'])
        self.end = iso_date(document['coverage']['end'])
        if not 0 < (self.end-self.start).days < MAX_DAYS:
            raise ValueError('Invalid or excessive calendar coverage')
        sessions = document['sessions']
        if not 1 <= len(sessions) <= MAX_DAYS:
            raise ValueError('Invalid session count')
        dates = [row['date'] for row in sessions]
        if dates != sorted(set(dates)):
            raise ValueError('Sessions must be unique and sorted')
        for row in sessions:
            day = iso_date(row['date'])
            if not self.start <= day <= self.end:
                raise ValueError('Session outside declared coverage')
            if utc_time(row['open_at']) >= utc_time(row['close_at']):
                raise ValueError('Invalid session boundaries')
        self._sessions = {row['date']: deepcopy(row) for row in sessions}
        expirations = document['expirations']
        if len(expirations) > MAX_DAYS*2:
            raise ValueError('Excessive expiration count')
        self._expirations = {}
        for row in expirations:
            key = row['expiration_id']
            if key in self._expirations or row['date'] not in self._sessions:
                raise ValueError('Duplicate expiration or non-session expiration date')
            if row['status'] != 'rule_candidate':
                raise ValueError('This snapshot schema does not certify listed contracts')
            if (row['root'], row['settlement']) not in (('SPX', 'AM'), ('SPXW', 'PM')):
                raise ValueError('Unsupported product/settlement combination')
            if row['settlement'] == 'PM' and row['settlement_reference_at'] != self._sessions[row['date']]['close_at']:
                raise ValueError('PM settlement must match underlying cash close')
            self._expirations[key] = deepcopy(row)

    def _range(self, start: str, end: str):
        left, right = iso_date(start), iso_date(end)
        if not self.start <= left <= right <= self.end:
            raise ValueError('Requested interval is outside calendar coverage; refresh explicitly')

    def sessions(self, start: str, end: str) -> list[dict]:
        self._range(start, end)
        return deepcopy([v for k, v in self._sessions.items() if start <= k <= end])

    def expirations(self, start: str, end: str, root: str = 'SPXW') -> list[dict]:
        self._range(start, end)
        if root not in ('SPX', 'SPXW'):
            raise ValueError('Supported roots are SPX and SPXW')
        if start < self._document['expiration_rule_coverage']['start']:
            raise ValueError('Historical expiration rules before 2023 are not modeled')
        return deepcopy(sorted((r for r in self._expirations.values()
                                if r['root'] == root and start <= r['date'] <= end),
                               key=lambda r: r['date']))

    def forecast_interval(self, cutoff: str, expiration_id: str, *, allow_rule_candidate: bool = False) -> dict:
        """Produce the interval consumed by run_expiry_forecast, without I/O.

        Explicit opt-in is required because the calendar is reference data,
        not proof a strike/expiry was listed at the historical cutoff.
        """
        if expiration_id not in self._expirations:
            raise ValueError('Unknown expiration ID; no nearest-date substitution')
        expiration = self._expirations[expiration_id]
        if not allow_rule_candidate:
            raise ValueError('Contract listing unverified; exploratory research requires allow_rule_candidate=True')
        if expiration['settlement'] != 'PM':
            raise ValueError('Daily-close model cannot forecast to AM settlement')
        end = expiration['date']
        self._range(cutoff, end)
        if cutoff not in self._sessions or cutoff >= end:
            raise ValueError('Cutoff must be a prior cash-session close')
        endpoints = [r['date'] for r in self.sessions(cutoff, end) if r['date'] > cutoff]
        return {
            'cutoff': cutoff, 'expiration': end, 'interval_end_dates': endpoints,
            'boundary_precision': 'daily_close',
            'calendar': {
                'calendar_id': self.calendar_id, 'version': self.version,
                'source': 'luca-calendar:sha256:' + self.sha256,
            },
        }

    def expiration(self, expiration_id: str) -> dict:
        return deepcopy(self._expirations[expiration_id])

    def reference(self) -> dict:
        return {k: deepcopy(self._document[k]) for k in
                ('calendar_id', 'version', 'sha256', 'coverage', 'expiration_rule_coverage', 'sources', 'limitations')}
