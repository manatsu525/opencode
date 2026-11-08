#!/usr/bin/env python3
"""Hidden controlling-TTY prompts, no-TTY/automation and piped installer regression tests."""
import argparse, errno, hashlib, json, os, pathlib, pty, select, signal, subprocess, sys, tempfile, time
from credentials import read_env, validate, write_env

here = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--frontend", required=True); parser.add_argument("--backend", required=True)
parser.add_argument("--arch", default=os.uname().machine)
parser.add_argument("--systemd", action="store_true", help="Also check actual systemd EnvironmentFile serialization (sudo, installed opencode user)")
args = parser.parse_args()
env = {key: value for key, value in os.environ.items() if key not in ("OPENCODE_WEB_USER", "OPENCODE_WEB_PASSWORD")}
checks = []
def check(name, condition):
    if not condition: raise AssertionError(name)
    checks.append(name)

def interactive(command, steps, child_env):
    pid, fd = pty.fork()
    if pid == 0: os.execvpe(command[0], command, child_env)
    output, pending = bytearray(), bytearray()
    def until(marker):
        deadline = time.monotonic() + 40
        while marker not in pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]: raise AssertionError("TTY prompt timeout: " + marker.decode())
            try: chunk = os.read(fd, 65536)
            except OSError as error:
                if error.errno == errno.EIO: chunk = b""
                else: raise
            if not chunk: raise AssertionError("TTY closed before prompt: " + marker.decode())
            output.extend(chunk); pending.extend(chunk)
        end = pending.index(marker) + len(marker); del pending[:end]
    try:
        for prompt, response in steps:
            until(prompt); os.write(fd, response + b"\n")
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                pid = None
                check("TTY command completed", os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0)
                break
            if select.select([fd], [], [], 0.1)[0]:
                try: output.extend(os.read(fd, 65536))
                except OSError as error:
                    if error.errno != errno.EIO: raise
        else: raise AssertionError("TTY command completion timeout")
        return bytes(output)
    finally:
        os.close(fd)
        if pid is not None:
            os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)

with tempfile.TemporaryDirectory(prefix="opencode-login-test-") as temp:
    root = pathlib.Path(temp); login = root / "login.json"
    command = [sys.executable, str(here / "credentials.py"), str(login)]
    result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, start_new_session=True)
    check("no TTY fails clearly", result.returncode != 0 and b"No controlling TTY" in result.stderr and not login.exists())
    for overrides in ({"OPENCODE_WEB_USER":"admin"}, {"OPENCODE_WEB_USER":"admin","OPENCODE_WEB_PASSWORD":""}, {"OPENCODE_WEB_USER":"bad:colon","OPENCODE_WEB_PASSWORD":"fake-test-secret"}, {"OPENCODE_WEB_USER":"admin","OPENCODE_WEB_PASSWORD":"   "}, {"OPENCODE_WEB_USER":"admin","OPENCODE_WEB_PASSWORD":"fake-test-secret\u0085"}):
        result = subprocess.run(command, env={**env, **overrides}, capture_output=True, start_new_session=True)
        check("partial/empty/unsafe automation rejected", result.returncode != 0 and b"fake-test-secret" not in result.stderr)
    test_password = "test $password \"quotes\" \\ trailing-space "
    result = subprocess.run(command, env={**env,"OPENCODE_WEB_USER":"automation-user","OPENCODE_WEB_PASSWORD":test_password}, capture_output=True, start_new_session=True)
    check("automation works without TTY and does not echo credentials", result.returncode == 0 and not result.stdout and test_password.encode() not in result.stderr)
    check("private staging file", login.stat().st_mode & 0o777 == 0o600)
    record = json.loads(login.read_text()); check("automation preserves special characters", record["password"] == test_password)
    file = root / "server.env"; write_env(file, {"OPENCODE_SERVER_USERNAME":"automation-user","OPENCODE_SERVER_PASSWORD":test_password})
    check("systemd environment quoting roundtrip", read_env(file)["OPENCODE_SERVER_PASSWORD"] == test_password)
    if args.systemd:
        if os.geteuid() != 0: raise SystemExit("--systemd requires root on a running systemd host")
        fixtures = {"OPENCODE_SERIALIZATION_" + str(i): value for i, value in enumerate((test_password, "tail\\", "quotes '\" and \\\\" , " spaces $ % 测试 ", "slash-quote " + chr(92) + chr(34), ""))}
        environment_file = root / "serialization.env"
        write_env(environment_file, fixtures)
        hashes = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in fixtures.items()}
        code = "import os,hashlib; expected=" + repr(hashes) + "; assert all(hashlib.sha256(os.environ[k].encode()).hexdigest()==v for k,v in expected.items())"
        result = subprocess.run(["systemd-run","--quiet","--wait","--collect","--pipe","--unit=opencode-credential-test-"+str(os.getpid()),"--uid=opencode","--property=EnvironmentFile="+str(environment_file),sys.executable,"-c",code],capture_output=True)
        check("real systemd special-character/Unicode/trailing-backslash serialization", result.returncode == 0)
    first, wrong, second = b"TTY-test-secret-one", b"TTY-wrong-secret", b"TTY-test-secret-two"
    steps = [(b"Login username [admin]: ", b""), (b"Login password (required): ", b""), (b"Login password (required): ", first), (b"Confirm password: ", wrong), (b"Login password (required): ", second), (b"Confirm password: ", second)]
    output = interactive(command, steps, env)
    check("TTY rejects empty password and retries mismatch", b"non-empty" in output and b"do not match" in output)
    check("TTY password and confirmation never echo", all(secret not in output for secret in (first, wrong, second)))
    check("TTY default admin and chosen confirmed password", json.loads(login.read_text()) == {"username":"admin","password":second.decode()})
    stage = root / "stage"; stage.mkdir()
    frontend = str(pathlib.Path(args.frontend).resolve()); backend = str(pathlib.Path(args.backend).resolve())
    sha = hashlib.sha256(pathlib.Path(frontend).read_bytes()).hexdigest()
    child_env = {**env,"DESTDIR":str(stage),"OPENCODE_ARCH":args.arch,"OPENCODE_LIBC":"glibc","OPENCODE_DEPLOY_DIR":str(here)}
    # This really pipes the installer through curl | bash; prompts must not consume script stdin.
    piped = ["bash","-c",'set -o pipefail; curl -fsS "file://$1/install.sh" | bash -s -- "${@:2}"',"test",str(here),"--host","127.0.0.1","--frontend-archive",frontend,"--frontend-sha256",sha,"--backend-archive",backend]
    for username, secret in ((b"first-admin", b"Piped-test-secret-one"), (b"second-admin", b"Piped-test-secret-two")):
        output = interactive(piped, [(b"Login username [admin]: ",username),(b"Login password (required): ",secret),(b"Confirm password: ",secret)], child_env)
        values = read_env(stage / "etc/opencode/server.env")
        check("curl pipe install/reinstall prompts from TTY", values["OPENCODE_SERVER_USERNAME"] == username.decode() and values["OPENCODE_SERVER_PASSWORD"] == secret.decode())
        check("piped installer password not echoed", secret not in output)
print(str(len(checks)) + " credential/TTY/piped-installer checks passed; no model calls.")
