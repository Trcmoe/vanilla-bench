"""Capture a launcher's Java command locally using its wrapper-command feature."""
import json
from pathlib import Path


def capture_command(command, output):
    if command and command[0] == '--': command = command[1:]
    command = list(command)
    if not command: raise ValueError('No Java command received from launcher')
    source = None
    for i, arg in enumerate(command):
        if arg == '--gameDir' and i + 1 < len(command):
            source = command[i + 1]
            command[i + 1] = '{game_dir}'
        elif arg.startswith('--gameDir='):
            source = arg.split('=', 1)[1]
            command[i] = '--gameDir={game_dir}'
    if source is None:
        raise ValueError('Expected launcher command with --gameDir; @argfiles must be expanded first')
    forbidden = ('--quickPlaySingleplayer', '--quickPlayMultiplayer', '--quickPlayRealms', '--server')
    if any(arg.split('=',1)[0] in forbidden for arg in command):
        raise ValueError('Disable launcher quick-play/server auto-join before capture')
    output = Path(output)
    # Exclusive creation prevents accidentally overwriting a known-good launch command.
    with output.open('x', encoding='utf-8') as stream:
        json.dump({'name':'EDIT PACK NAME', 'version':'EDIT PINNED VERSION',
                   'game_dir':str(Path(source).resolve()), 'command':command}, stream, indent=2)
    try: output.chmod(0o600)
    except OSError: pass
