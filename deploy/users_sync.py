#!/usr/bin/env python3
"""Root side of multi-user: start one opencode backend (opencode-user@NAME) per extra user listed by the gate.

The gate (unprivileged) writes /var/lib/opencode-auth/instances.json = {"users": {name: port}}; a systemd path unit
runs this script whenever it changes. Each user gets its own workspace, chat history (XDG data/state) and cache under
/var/lib/opencode/users/NAME; everything else (HOME, config, skills, the rest of the filesystem) is shared. A removed
user's backend is stopped and its folder is moved to /var/lib/opencode/users-deleted/, never deleted."""
import json, os, pathlib, re, shutil, sqlite3, subprocess, sys, time

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
    if changed:
        for _ in range(30):
            if (home / 'data/opencode/opencode.db').exists():break
            time.sleep(1)

CRED_COLUMNS = ('id', 'integration_id', 'label', 'value', 'connector_id', 'method_id', 'active', 'time_created', 'time_updated')
SHARED = ROOT / 'var/lib/opencode/state/shared-credentials.json'
PRIMARY_STATE = ROOT / 'var/lib/opencode/state/shared-credentials.ids'

def database(name):
    if name is None:return PRIMARY_DATA / 'opencode.db', PRIMARY_STATE
    return USERS / name / 'data/opencode/opencode.db', USERS / name / 'state/shared-credentials.ids'

def read_rows(path):
    connection = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=10)
    try:
        if not connection.execute("select 1 from sqlite_master where type='table' and name='credential'").fetchone():return None
        return {row[0]: list(row) for row in connection.execute('select %s from credential' % ', '.join('`%s`' % c for c in CRED_COLUMNS))}
    finally:connection.close()

def write_rows(path, current, shared):
    cols = ', '.join('`%s`' % c for c in CRED_COLUMNS);changed = False
    connection = sqlite3.connect(str(path), timeout=10)
    try:
        for key, row in shared.items():
            if current.get(key) != row:connection.execute('insert or replace into credential (%s) values (%s)' % (cols, ','.join('?' * len(CRED_COLUMNS))), row);changed = True
        for key in set(current) - set(shared):connection.execute('delete from credential where id = ?', (key,));changed = True
        connection.commit()
    finally:connection.close()
    return changed

def share_credentials(names):
    """Provider keys/logins (the `credential` table each backend reads live) are shared by every user. Only admins can
    change them (the gate refuses provider writes from other users), but an admin may be any user, so a change made in
    any user's database (or the primary's) is merged into one shared set, which is then written to every database. A
    row missing from a database counts as deleted only if that database already held it after the previous run."""
    try:shared = {key: list(row) for key, row in json.loads(SHARED.read_text()).items()}
    except (OSError, ValueError):shared = None
    found = {}
    for name in [None, *names]:
        path, state = database(name)
        if not path.exists():continue
        try:rows = read_rows(path)
        except sqlite3.Error as error:print('credential read for %s failed: %s' % (name or 'primary', error), file=sys.stderr);continue
        if rows is None:continue
        try:given = set(json.loads(state.read_text()))
        except (OSError, ValueError):given = None
        found[name] = (path, state, rows, given)
    if not found:return
    if shared is None:shared = dict(found[None][2]) if None in found else {}
    for name, (path, state, rows, given) in found.items():
        for key in (given or set()) - set(rows):shared.pop(key, None)
        for key, row in rows.items():
            if key not in shared or (row != shared[key] and (row[8] or 0) >= (shared[key][8] or 0)):shared[key] = row
    SHARED.parent.mkdir(parents=True, exist_ok=True);tmp = SHARED.with_suffix('.tmp')
    tmp.write_text(json.dumps(shared));tmp.chmod(0o600);tmp.replace(SHARED)
    for name, (path, state, rows, given) in found.items():
        try:write_rows(path, rows, shared)
        except sqlite3.Error as error:print('credential write for %s failed: %s' % (name or 'primary', error), file=sys.stderr);continue
        state.parent.mkdir(parents=True, exist_ok=True);state.write_text(json.dumps(sorted(shared)));state.chmod(0o600)

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
    share_credentials(sorted(users))
    return 0

if __name__ == '__main__':sys.exit(main())
