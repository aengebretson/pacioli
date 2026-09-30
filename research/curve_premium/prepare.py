"""Save immutable predeclaration before inventory/forecast/outcome evaluation."""
import argparse
from pathlib import Path
from common import digest, existing_output, now, write_json
from predeclare import SPEC

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    out=existing_output(parser.parse_args().output)
    if (out/'predeclaration.json').exists():raise ValueError('predeclaration already exists')
    write_json(out/'predeclaration.json',{**SPEC,'declared_at':now(),'source_sha256':digest(Path(__file__).with_name('predeclare.py'))})
