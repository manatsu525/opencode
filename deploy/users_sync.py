#!/usr/bin/env python3
"""Root side of multi-user: start one opencode backend (opencode-user@NAME) per extra user listed by the gate.

The gate (unprivileged) writes /var/lib/opencode-auth/instances.json = {"users": {name: port}}; a systemd path unit
runs this script whenever it changes. Each user gets its own workspace, chat history (XDG data/state) and cache under
/var/lib/opencode/users/NAME; everything else (HOME, config, skills, the rest of the filesystem) is shared. A removed
user's backend is stopped and its folder is moved to /var/lib/opencode/users-deleted/, never deleted."""
import json, os, pathlib, re, shutil, subprocess, sys, time

ROOT = pathlib.Path(os.environ.get('OPENCODE_SYNC_ROOT', '/'))
INSTANCES = ROOT / 'var/lib/opencode-auth/instances.json'
USERS = ROOT / 'var/lib/opencode/users'
ARCHIVE = ROOT / 'var/lib/opencode/users-deleted'
ENVS = ROOT / 'etc/opencode/users'
PRIMARY_DATA = ROOT / 'var/lib/opencode/data/opencode'
NAME = re.compile(r'[a-z][a-z0-9_-]{0,31}')

def systemctl(*args, check=False):
    if os.environ.get('OPENCODE_SYNC_DRY'):print('systemctl', *args);return 0
    return subprocess.run(['systemctl', *args], check=check).returncode

def wanted():
    try:data = json.loads(INSTANCES.read_text())
    except (OSError, ValueError):return None
    result = {}
    for name, port in (data.get('users') or {}).items():
        if isinstance(name, str) and NAME.fullmatch(name) and isinstance(port, int) and 4101 <= port <= 4999:result[name] = port
    return result

def ensure(name, port):
    home = USERS / name
    for sub in ('', 'workspace', 'data', 'data/opencode', 'state', 'cache'):
        folder = home / sub;folder.mkdir(parents=True, exist_ok=True);folder.chmod(0o700)
    # Share provider logins made in the UI (auth.json) with the primary user, like every other shared setting.
    auth = PRIMARY_DATA / 'auth.json';link = home / 'data/opencode/auth.json'
    if auth.exists() and not link.exists() and not link.is_symlink():link.symlink_to(auth)
    ENVS.mkdir(parents=True, exist_ok=True);ENVS.chmod(0o755)
    env = ENVS / (name + '.env')
    text = 'OPENCODE_PORT=%d\nOPENCODE_WORKSPACE=%s\n' % (port, '/var/lib/opencode/users/' + name + '/workspace')
    changed = not env.exists() or env.read_text() != text
    if changed:env.write_text(text);env.chmod(0o644)
    unit = 'opencode-user@' + name + '.service'
    systemctl('enable', unit)
    if changed:systemctl('restart', unit)
    else:systemctl('start', unit)

def remove(name):
    unit = 'opencode-user@' + name + '.service'
    systemctl('disable', '--now', unit)
    env = ENVS / (name + '.env')
    if env.exists():env.unlink()
    home = USERS / name
    if home.exists():
        ARCHIVE.mkdir(parents=True, exist_ok=True);ARCHIVE.chmod(0o700)
        shutil.move(str(home), str(ARCHIVE / (name + '-' + time.strftime('%Y%m%d-%H%M%S'))))
    systemctl('reset-failed', unit)

def main():
    users = wanted()
    if users is None:return 0  # no gate state yet: nothing to do, never tear anything down
    existing = {file.stem for file in ENVS.glob('*.env')} if ENVS.exists() else set()
    for name, port in sorted(users.items()):ensure(name, port)
    for name in sorted(existing - set(users)):
        if NAME.fullmatch(name):remove(name)
    return 0

if __name__ == '__main__':sys.exit(main())
