"""Isolated sequential runs. No authentication, shell execution, or global process kills."""
import json
import math
import os
import platform
import random
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

import psutil
from .config import fingerprint


def save_json(path, data):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def host_info():
    return {'os': platform.platform(), 'python': platform.python_version(),
            'cpu': platform.processor(), 'logical_cpus': psutil.cpu_count(),
            'physical_cpus': psutil.cpu_count(logical=False),
            'total_memory_bytes': psutil.virtual_memory().total}


def prepare_game(config, pack, directory):
    source = Path(pack['game_dir'])
    game = directory / 'game'
    # A fresh copy for every launch, excluding potentially huge unrelated worlds/logs.
    def ignore(path, names):
        return [n for n in names if n in ('logs', 'crash-reports', 'session.lock') or
                (Path(path) == source and n in ('saves', 'screenshots'))]
    shutil.copytree(source, game, ignore=ignore)
    world = game / 'saves' / 'vanilla-bench-world'
    shutil.copytree(config['world_template'], world, ignore=shutil.ignore_patterns('session.lock'))
    mods = game / 'mods'
    mods.mkdir(exist_ok=True)
    # Refuse double instrumentation instead of silently testing with two probes.
    for jar in mods.glob('*.jar'):
        try:
            with zipfile.ZipFile(jar) as archive:
                info = json.loads(archive.read('fabric.mod.json'))
            if info.get('id') == 'vanillabenchprobe':
                raise ValueError('Remove the benchmark probe from the source instance; runner installs it')
        except (KeyError, zipfile.BadZipFile):
            pass
    shutil.copy2(config['probe_jar'], mods / Path(config['probe_jar']).name)
    options_path = game / 'options.txt'
    lines = options_path.read_text(encoding='utf-8').splitlines() if options_path.exists() else []
    overrides = {str(k): str(v) for k, v in config['options'].items()}
    lines = [line for line in lines if line.partition(':')[0] not in overrides]
    lines.extend(f'{key}:{value}' for key, value in overrides.items())
    options_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return game


class Protocol:
    def __init__(self, run_id):
        self.run_id = run_id
        self.events = []
        self.frames = []
        self.stage = 'new'
        self.pid = None
        self.menu = None
        self.world = None
        self.start = None
        self.end = None
        self.previous_time = -1

    def accept(self, event):
        if event.get('run_id') != self.run_id:
            raise ValueError('Telemetry run_id mismatch')
        kind = event.get('type')
        if kind == 'error':
            raise ValueError(f'Probe: {event.get("message", "unknown error")}')
        transitions = {'hello': ('new', 'hello'), 'menu': ('hello', 'menu'),
                       'world_ready': ('menu', 'world'), 'measurement_start': ('world', 'measuring'),
                       'measurement_end': ('measuring', 'done')}
        if kind == 'frames':
            values = event.get('frame_ms')
            if self.stage != 'measuring' or not isinstance(values, list) or not values:
                raise ValueError('Unexpected or empty frame batch')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
                raise ValueError('Frame intervals must be finite positive milliseconds')
            self.frames.extend(values)
            return
        if kind not in transitions or self.stage != transitions[kind][0]:
            raise ValueError(f'Out-of-order telemetry event: {kind}')
        stamp = event.get('jvm_uptime_ms')
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp < self.previous_time:
            raise ValueError('Missing or non-monotonic JVM uptime')
        self.previous_time = stamp
        if kind == 'hello':
            self.pid = event.get('pid')
            if not isinstance(self.pid, int) or isinstance(self.pid, bool) or self.pid <= 0:
                raise ValueError('Invalid game PID')
        if kind == 'menu': self.menu = stamp
        if kind == 'world_ready': self.world = stamp
        if kind == 'measurement_start': self.start = stamp
        if kind == 'measurement_end': self.end = stamp
        self.stage = transitions[kind][1]
        self.events.append(event)


def descendants(root, owned):
    try:
        for proc in [root, *root.children(recursive=True)]:
            owned[(proc.pid, proc.create_time())] = proc
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def stop_owned(owned):
    living = []
    for proc in reversed(list(owned.values())):
        try:
            if proc.is_running():
                proc.terminate()
                living.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, remaining = psutil.wait_procs(living, timeout=5)
    for proc in remaining:
        try: proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    psutil.wait_procs(remaining, timeout=3)


def check_effective_settings(config, event):
    settings = event.get('effective_settings')
    if not isinstance(settings, dict):
        raise ValueError('Probe did not supply effective graphics settings')
    numeric = {'renderDistance': 'render_distance', 'simulationDistance': 'simulation_distance',
               'maxFps': 'max_fps', 'overrideWidth': 'window_width', 'overrideHeight': 'window_height'}
    boolean = {'enableVsync': 'vsync', 'fullscreen': 'fullscreen'}
    for option, field in numeric.items():
        if option in config['options'] and settings.get(field) != int(config['options'][option]):
            raise ValueError(f'Effective {field} differs from configured {option}')
    for option, field in boolean.items():
        if option in config['options'] and settings.get(field) != (str(config['options'][option]).lower() == 'true'):
            raise ValueError(f'Effective {field} differs from configured {option}')


def comparison_profile(run):
    hello = next(e for e in run['events'] if e['type'] == 'hello')
    world = next(e for e in run['events'] if e['type'] == 'world_ready')
    return {'java_version': hello.get('java_version'), 'max_heap_bytes': hello.get('max_heap_bytes'),
            'effective_settings': world.get('effective_settings'),
            'viewpoint': {k: world.get(k) for k in ('player_x','player_y','player_z','start_yaw','start_pitch')}}


def one_run(config, pack, scenario, repetition, directory):
    directory.mkdir(parents=True)
    run_id = str(uuid.uuid4())
    run = {'pack': pack['name'], 'version': pack['version'], 'scenario': scenario,
           'repetition': repetition, 'run_id': run_id, 'status': 'failed', 'error': None,
           'startup_ms': None, 'world_load_ms': None, 'frames_ms': [], 'resources': [], 'events': []}
    owned = {}
    process = None
    protocol = Protocol(run_id)
    try:
        game = prepare_game(config, pack, directory)
        output = (directory / 'telemetry.jsonl').resolve()
        output.touch()
        env = os.environ.copy()
        env.update({'VANILLA_BENCH_OUTPUT': str(output), 'VANILLA_BENCH_RUN_ID': run_id,
                    'VANILLA_BENCH_WORLD': 'vanilla-bench-world',
                    'VANILLA_BENCH_WARMUP': str(config['warmup_seconds']),
                    'VANILLA_BENCH_DURATION': str(config['duration_seconds']),
                    'VANILLA_BENCH_SCENARIO': scenario})
        command = [arg.replace('{game_dir}', str(game.resolve())) for arg in pack['command']]
        start = time.monotonic()
        with (directory / 'process.log').open('wb') as log, output.open(encoding='utf-8') as stream:
            process = subprocess.Popen(command, cwd=game, env=env, stdout=log, stderr=subprocess.STDOUT, shell=False)
            root = psutil.Process(process.pid)
            descendants(root, owned)
            pending = ''
            tracked = None
            last_sample = start
            sample_start = None
            next_sample = start
            while time.monotonic() - start < config['timeout_seconds']:
                descendants(root, owned)
                pending += stream.read()
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if not line.strip(): continue
                    event = json.loads(line)
                    protocol.accept(event)
                    if event['type'] == 'world_ready':
                        check_effective_settings(config, event)
                    if event['type'] == 'hello':
                        descendants(root, owned)
                        matches = [p for p in owned.values() if p.pid == protocol.pid and p.is_running()]
                        if not matches:
                            raise ValueError('Probe PID is not in the launched process tree; launch Java directly')
                        tracked = matches[0]
                    if event['type'] == 'measurement_start':
                        if tracked is None: raise ValueError('No game process')
                        tracked.cpu_percent(None)  # Prime before collecting the first nonzero interval.
                        sample_start = time.monotonic()

                        last_sample = sample_start
                        next_sample = sample_start + config['sample_interval_seconds']
                now = time.monotonic()
                if protocol.stage == 'done': break
                if tracked is not None and protocol.stage == 'measuring' and now >= next_sample:
                    with tracked.oneshot():
                        try: io = tracked.io_counters()
                        except (AttributeError, psutil.AccessDenied): io = None
                        run['resources'].append({'elapsed_s': now - sample_start,
                            'interval_s': now - last_sample, 'cpu_percent': tracked.cpu_percent(None),
                            'rss_bytes': tracked.memory_info().rss,
                            'read_bytes': io.read_bytes if io else None, 'write_bytes': io.write_bytes if io else None,
                            'system_memory_percent': psutil.virtual_memory().percent})
                    last_sample = now
                    next_sample = now + config['sample_interval_seconds']
                if process.poll() is not None and not any(p.is_running() for p in owned.values()):
                    raise ValueError('Game exited before measurement completed')
                time.sleep(min(.05, config['sample_interval_seconds']))
            if protocol.stage != 'done': raise TimeoutError('Timed out waiting for complete probe telemetry')
            if len(protocol.frames) < 2 or sum(protocol.frames) < config['duration_seconds'] * 1000 * .9:
                raise ValueError('Insufficient frame coverage for the requested measurement duration')
            elapsed = protocol.end - protocol.start
            end_event = next(e for e in protocol.events if e['type'] == 'measurement_end')
            if end_event.get('sample_count') != len(protocol.frames):
                raise ValueError('Frame sample count differs from probe completion record')
            if elapsed < config['duration_seconds'] * 1000 - 20:
                raise ValueError('Probe measurement ended before requested duration')
            if abs(sum(protocol.frames) - elapsed) > max(20, elapsed * .01):
                raise ValueError('Frame durations do not cover the measurement event interval')
            if not run['resources']:
                raise ValueError('No process resource samples captured')
            run.update(status='ok', startup_ms=protocol.menu, world_load_ms=protocol.world - protocol.menu,
                       launch_to_end_s=time.monotonic() - start)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: pass
    except Exception as exc:
        run['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if process is not None:
            stop_owned(owned)
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        run['frames_ms'] = protocol.frames
        run['events'] = protocol.events
        save_json(directory / 'run.json', run)
    return run


def run_suite(config, output_dir):
    output = Path(output_dir).resolve()
    for source in [config['world_template'], *[p['game_dir'] for p in config['packs']]]:
        source = Path(source).resolve()
        if output == source or output.is_relative_to(source):
            raise ValueError('Output directory must be outside source instances and world template')
    output.mkdir(parents=True, exist_ok=False)
    metadata = {'host': host_info(), 'minecraft_version': config['minecraft_version'],
                'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'world_sha256': fingerprint(Path(config['world_template'])),
                'probe_sha256': fingerprint(Path(config['probe_jar'])),
                'options_overrides': config['options'], 'warmup_seconds': config['warmup_seconds'],
                'duration_seconds': config['duration_seconds'], 'seed': config['seed'],
                'cache_policy': 'uncontrolled OS cache; first launch retained and labelled by repetition',
                'packs': []}
    for pack in config['packs']:
        base = Path(pack['game_dir'])
        metadata['packs'].append({'name': pack['name'], 'version': pack['version'],
            'fingerprints': {name: fingerprint(base / name) for name in ('mods', 'config', 'options.txt') if (base / name).exists()}})
    results = {'schema_version': 1, 'synthetic': False, 'metadata': metadata, 'runs': []}
    save_json(output / 'results.json', results)
    rng = random.Random(config['seed'])
    schedule = []
    for repetition in range(1, config['repetitions'] + 1):
        block = [(p, s, repetition) for p in config['packs'] for s in config['scenarios']]
        rng.shuffle(block)
        schedule.extend(block)
    try:
        for index, (pack, scenario, repetition) in enumerate(schedule, 1):
            print(f'[{index}/{len(schedule)}] {pack["name"]} / {scenario} / repeat {repetition}', flush=True)
            run = one_run(config, pack, scenario, repetition, output / f'run-{index:03d}')
            if run['status'] == 'ok':
                profile = comparison_profile(run)
                if 'comparison_profile' not in metadata:
                    metadata['comparison_profile'] = profile
                elif profile != metadata['comparison_profile']:
                    run.update(status='failed', error='Effective settings, Java/heap or saved viewpoint differ from the first successful run')
                    save_json(output / f'run-{index:03d}' / 'run.json', run)
            results['runs'].append(run)
            save_json(output / 'results.json', results)
            from .report import build_report
            build_report(results, output)
            if index < len(schedule): time.sleep(config['cooldown_seconds'])
    finally:
        from .report import build_report
        build_report(results, output)
    return results
