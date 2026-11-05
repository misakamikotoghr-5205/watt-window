import argparse
import json
from pathlib import Path
import sys

from .core import InputError, sensitivity, solve
from .export import export_bundle, export_sensitivity


def load(path):
    data = Path(path).read_bytes()
    if len(data) > 200000: raise InputError('Input exceeds 200 KB')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise InputError('Duplicate JSON field')
            value[key] = item
        return value
    def reject(_value): raise InputError('Nonfinite JSON number')
    try: return json.loads(data, object_pairs_hook=unique, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError) as exc: raise InputError('Invalid JSON input') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description='Watt Window: advisory noncritical-load scheduling; no device control')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['solve', 'sensitivity']:
        item = sub.add_parser(command); item.add_argument('problem'); item.add_argument('--max-nodes', type=int, default=100000)
        item.add_argument('--out')
        if command == 'sensitivity': item.add_argument('--scenarios', required=True)
    args = parser.parse_args(argv)
    try:
        data = load(args.problem)
        result = solve(data, args.max_nodes) if args.command == 'solve' else sensitivity(data, load(args.scenarios), args.max_nodes)
        if args.command == 'solve' and args.out: result['export_directory'] = export_bundle(result, args.out)
        elif args.out: result['export_directory'] = export_sensitivity(result, args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (InputError, OSError) as error:
        print(json.dumps({'error': str(error), 'device_commands_sent': 0}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
