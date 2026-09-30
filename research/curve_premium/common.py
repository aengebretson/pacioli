"""Artifact I/O: local, bounded, explicit paths; no network access."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def record(stream, value):
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


def checkpoint(output, phase, **details):
    output = Path(output)
    path = output / 'STATUS.json'
    status = json.loads(path.read_text()) if path.exists() else {'task': 'Q2-T18', 'status': 'in_progress'}
    status.update(updated_at=now(), phase=phase, **details)
    write_json(path, status)
    with (output / 'STATUS.md').open('a') as stream:
        stream.write(f'\nCheckpoint {status["updated_at"]}: {phase}. {json.dumps(details)}\n')
    inbox = output / 'INBOX.md'
    if inbox.exists():
        print('INBOX:', inbox.read_text().strip(), flush=True)
    print(phase, details, flush=True)


def existing_output(value):
    path = Path(value).resolve()
    if path.name != 'output':
        raise ValueError('Artifacts must be written to a directory named output outside the repository')
    repo = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repo):
        raise ValueError('Generated data/results must stay outside Git')
    path.mkdir(parents=True, exist_ok=True)
    return path
