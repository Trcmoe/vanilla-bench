"""Strict configuration and immutable input fingerprints."""
import hashlib
import json
import math
from pathlib import Path


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    for item in files:
        if item.is_symlink():
            raise ValueError(f'Symlinks are not supported: {item}')
        digest.update((item.relative_to(path).as_posix() if path.is_dir() else item.name).encode())
        with item.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    return digest.hexdigest()


def load_config(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('minecraft_version') != '1.20.1':
        raise ValueError('Bundled probe supports exactly Minecraft 1.20.1')
    for key, default, minimum in [('repetitions', 5, 1), ('warmup_seconds', 30, 0),
                                  ('duration_seconds', 120, 1), ('timeout_seconds', 600, 1),
                                  ('sample_interval_seconds', .5, .05), ('cooldown_seconds', 10, 0)]:
        value = data.setdefault(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
            raise ValueError(f'Invalid {key}')
    if not isinstance(data['repetitions'], int):
        raise ValueError('repetitions must be an integer')
    if data['timeout_seconds'] <= data['warmup_seconds'] + data['duration_seconds']:
        raise ValueError('timeout must allow startup, warmup and measurement')
    if data['sample_interval_seconds'] >= data['duration_seconds']:
        raise ValueError('sample_interval_seconds must be smaller than duration_seconds')
    if data['warmup_seconds'] > 3600 or data['duration_seconds'] > 3600:
        raise ValueError('Probe warmup and duration must not exceed 3600 seconds')
    packs = data.get('packs', [])
    if not packs or len({p['name'] for p in packs}) != len(packs):
        raise ValueError('At least one pack and unique names required')
    scenarios = data.setdefault('scenarios', ['static', 'rotate'])
    if not scenarios or len(set(scenarios)) != len(scenarios) or any(s not in ('static', 'rotate') for s in scenarios):
        raise ValueError('scenarios must contain unique static/rotate entries')
    data.setdefault('seed', 20260924)
    data.setdefault('options', {'enableVsync':'false', 'maxFps':'260', 'pauseOnLostFocus':'false',
                                'renderDistance':'12', 'simulationDistance':'8', 'fullscreen':'false',
                                'overrideWidth':'1920', 'overrideHeight':'1080'})
    for key in ['world_template', 'probe_jar']:
        data[key] = str((path.parent / data[key]).resolve())
        if not Path(data[key]).exists():
            raise ValueError(f'Missing {key}: {data[key]}')
    if not (Path(data['world_template']) / 'level.dat').is_file():
        raise ValueError('world_template must be a prepared Minecraft save with level.dat')
    if not Path(data['probe_jar']).is_file():
        raise ValueError('probe_jar must be a file')
    for pack in packs:
        if not pack.get('version') or not pack.get('name'):
            raise ValueError('Each pack requires name and pinned version')
        pack['game_dir'] = str((path.parent / pack['game_dir']).resolve())
        if not Path(pack['game_dir']).is_dir():
            raise ValueError(f'Missing game_dir for {pack["name"]}')
        command = pack.get('command')
        if not isinstance(command, list) or not command or not all(isinstance(s,str) and s for s in command):
            raise ValueError('command must be a nonempty argument array (never a shell string)')
        if not any('{game_dir}' in s for s in command):
            raise ValueError('command must use {game_dir} so original instances remain untouched')
        if any(p.is_symlink() for p in Path(pack['game_dir']).rglob('*')):
            raise ValueError('Instance symlinks are not supported')
    return data
