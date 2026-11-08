#!/usr/bin/env python3
"""TTY-only hidden prompts / explicit automation input; no credential stdout or argv."""
import io, json, os, pathlib, re, shlex, sys, tempfile, termios

def validate(user, password):
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", user):
        raise ValueError("Username must be 1-64 ASCII letters/digits or _ . @ - (no colon)")
    if not password.strip() or not password.isprintable():
        raise ValueError("Password must be non-empty and contain no control characters")

def read_env(file):
    values = {}
    if not pathlib.Path(file).exists(): return values
    for line in pathlib.Path(file).read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value, comments=False)
        values[key] = parsed[0] if len(parsed) == 1 else value
    return values

def atomic_write(file, text, mode=0o600):
    file = pathlib.Path(file); file.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".credentials-", dir=str(file.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream: stream.write(text)
        os.replace(name, file)
    finally:
        if os.path.exists(name): os.unlink(name)

def write_env(file, values):
    # Ubuntu 20.04 systemd's double-quoted parser retains doubled backslashes.
    # Unquoted literal escapes roundtrip both old systemd and POSIX shlex.
    def quote(value):
        return re.sub(r"([^A-Za-z0-9_./:@+-])", lambda match: "\\" + match.group(1), value)
    atomic_write(file, "".join(key + "=" + quote(value) + "\n" for key, value in values.items()))

def collect():
    keys = ("OPENCODE_WEB_USER", "OPENCODE_WEB_PASSWORD")
    if any(key in os.environ for key in keys):
        if not all(os.environ.get(key) for key in keys):
            raise ValueError("Set BOTH non-empty OPENCODE_WEB_USER and OPENCODE_WEB_PASSWORD for automation")
        result = (os.environ[keys[0]], os.environ[keys[1]])
        validate(*result); return result
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        tty = io.TextIOWrapper(io.FileIO(fd, "w+"), line_buffering=True)
    except OSError:
        raise ValueError("No controlling TTY: set BOTH OPENCODE_WEB_USER and OPENCODE_WEB_PASSWORD")
    with tty:
        tty.write("Login username [admin]: "); tty.flush()
        line = tty.readline()
        if not line: raise ValueError("Login setup cancelled (EOF)")
        user = line.rstrip("\r\n") or "admin"
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", user):
            raise ValueError("Invalid username (no colon/control characters)")
        def hidden(prompt):
            old = termios.tcgetattr(tty.fileno()); new = old[:]
            new[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(tty.fileno(), termios.TCSANOW, new)
            tty.write(prompt); tty.flush()
            try: value = tty.readline()
            finally:
                termios.tcsetattr(tty.fileno(), termios.TCSADRAIN, old)
                tty.write("\n"); tty.flush()
            if not value: raise ValueError("Login setup cancelled (EOF)")
            return value.rstrip("\r\n")
        while True:
            password = hidden("Login password (required): ")
            try: validate(user, password)
            except ValueError:
                tty.write("Password must be non-empty, without control characters. Try again.\n"); continue
            confirm = hidden("Confirm password: ")
            if password == confirm: return user, password
            tty.write("Passwords do not match. Try again.\n")

if __name__ == "__main__":
    try:
        user, password = collect()
        atomic_write(sys.argv[1], json.dumps({"username":user, "password":password}))
    except (ValueError, KeyboardInterrupt, termios.error) as error:
        print("Login setup failed: " + (str(error) if not isinstance(error, KeyboardInterrupt) else "cancelled"), file=sys.stderr)
        sys.exit(1)
