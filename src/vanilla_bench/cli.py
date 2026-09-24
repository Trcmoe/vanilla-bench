import argparse
import json
import random
import sys
from pathlib import Path

from .config import load_config
from .report import build_report
from .runner import run_suite, save_json


def demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(71)
    results = {'schema_version': 1, 'synthetic': True,
               'metadata': {'notice': 'SYNTHETIC demonstration only. Not measured Minecraft performance.'}, 'runs': []}
    for pack, base in [('Demo Pack A', 8), ('Demo Pack B', 10), ('Demo Pack C', 12)]:
        for scenario in ['static', 'rotate']:
            for repetition in range(1, 6):
                frames = [max(1, rng.gauss(base, 1.2)) for _ in range(1000)]
                frames[500] = 100
                results['runs'].append({'pack': pack, 'scenario': scenario, 'repetition': repetition,
                    'status': 'ok', 'error': None, 'startup_ms': 4000 + rng.random()*1000,
                    'world_load_ms': 2000 + rng.random()*500, 'frames_ms': frames,
                    'resources': [{'elapsed_s': i*.5, 'cpu_percent': 150+rng.random()*80,
                                   'rss_bytes': int((1200+rng.random()*100)*1024**2),
                                   'read_bytes': None, 'write_bytes': None, 'system_memory_percent': 30}
                                  for i in range(16)], 'events': []})
    save_json(output / 'results.json', results)
    build_report(results, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reproducible Minecraft modpack benchmark')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ['validate', 'run']:
        command = sub.add_parser(action)
        command.add_argument('config', type=Path)
        if action == 'run': command.add_argument('--output', required=True, type=Path)
    command = sub.add_parser('report')
    command.add_argument('results', type=Path)
    command.add_argument('--output', required=True, type=Path)
    command = sub.add_parser('demo')
    command.add_argument('--output', required=True, type=Path)
    command = sub.add_parser('catalog')
    command.add_argument('--project', action='append', required=True,
                         help='Modrinth project slug or ID; repeat for each pack to compare')
    command.add_argument('--minecraft', default='1.20.1')
    command.add_argument('--output', required=True, type=Path)
    command = sub.add_parser('capture', help='Launcher wrapper: capture Java arguments locally without launching')
    command.add_argument('--output', required=True, type=Path)
    command.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == 'validate':
            config = load_config(args.config)
            print(f'Valid configuration: {len(config["packs"])} packs; probe supports Minecraft 1.20.1')
        elif args.action == 'run':
            results = run_suite(load_config(args.config), args.output)
            print(f'Report: {(args.output / "report.html").resolve()}')
            return 1 if any(r['status'] != 'ok' for r in results['runs']) else 0
        elif args.action == 'report':
            build_report(json.loads(args.results.read_text(encoding='utf-8')), args.output)
        elif args.action == 'demo': demo(args.output)
        elif args.action == 'capture':
            from .capture import capture_command
            capture_command(args.command, args.output)
            print('Captured local launch command. It may contain an account token; do not publish it.')
        elif args.action == 'catalog':
            from .catalog import resolve
            if args.output.exists(): raise ValueError('Catalog output already exists; choose a new lock file')
            save_json(args.output, resolve(args.project, args.minecraft))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; completed run data retained.', file=sys.stderr)
        return 130
