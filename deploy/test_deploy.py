#!/usr/bin/env python3
"""Safe AMD64 staging/idempotence/purge and native backend smoke test (no system changes)."""
import argparse, base64, hashlib, io, json, os, pathlib, socket, subprocess, tarfile, tempfile, time, urllib.error, urllib.request
from credentials import read_env
parser=argparse.ArgumentParser();parser.add_argument("--frontend",required=True);parser.add_argument("--backend",required=True);parser.add_argument("--report",required=True);args=parser.parse_args()
here=pathlib.Path(__file__).resolve().parent
sha=hashlib.sha256(pathlib.Path(args.frontend).read_bytes()).hexdigest()
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)
with tempfile.TemporaryDirectory(prefix="opencode-deploy-test-") as temp:
    root=pathlib.Path(temp)/"root";root.mkdir()
    env={**os.environ,"DESTDIR":str(root),"OPENCODE_ARCH":"x86_64","OPENCODE_LIBC":"glibc","OPENCODE_WEB_USER":"test-admin","OPENCODE_WEB_PASSWORD":"test password $special \"quoted\"\\end"}
    command=["bash",str(here/"install.sh"),"--host","127.0.0.1","--frontend-archive",str(pathlib.Path(args.frontend).resolve()),"--frontend-sha256",sha,"--backend-archive",str(pathlib.Path(args.backend).resolve())]
    def install():subprocess.run(command,env=env,check=True,stdout=subprocess.DEVNULL)
    install()
    config_path=root/"etc/opencode/opencode.json"
    check("keyless Keenable remote installed with OAuth disabled", json.loads(config_path.read_text())["mcp"]["keenable_search"]["oauth"] is False)
    check("installer/uninstaller retained",(root/"opt/opencode/deploy/uninstall.sh").is_file())
    short=root/"usr/local/bin/opencode-uninstall"
    check("standalone opencode-uninstall short command installed",short.is_file() and os.access(short,os.X_OK) and short.read_bytes()==(here/"uninstall.sh").read_bytes() and b"common.sh\"" not in short.read_bytes())
    credential=root/"etc/opencode/server.env";secret_hash=hashlib.sha256(credential.read_bytes()).hexdigest();cert_hash=hashlib.sha256((root/"etc/opencode/tls/cert.pem").read_bytes()).hexdigest()
    check("root-only credential mode",credential.stat().st_mode&0o777==0o600)
    check("web unit is unprivileged","User=opencode-web" in (root/"etc/systemd/system/opencode-web.service").read_text())
    backend_unit=(root/"etc/systemd/system/opencode.service").read_text()
    check("backend explicitly runs as root with unchanged XDG state", "User=root" in backend_unit and "HOME=/var/lib/opencode" in backend_unit and "ProtectHome=false" in backend_unit)
    check("wildcard and specific default permissions all allow",set(json.loads((root/"etc/opencode/opencode.json").read_text())["permission"].values())=={"allow"})
    check("auth helper isolated and cookie-gated proxy generated", "User=opencode-auth" in (root/"etc/systemd/system/opencode-auth.service").read_text() and "auth_request /_opencode_auth" in (root/"etc/opencode/nginx.conf").read_text())
    check("PWA manifest icons explicitly public", "web-app-manifest[^/]*" in (root/"etc/opencode/nginx.conf").read_text())
    install()
    check("idempotent server password",hashlib.sha256(credential.read_bytes()).hexdigest()==secret_hash)
    check("idempotent certificate",hashlib.sha256((root/"etc/opencode/tls/cert.pem").read_bytes()).hexdigest()==cert_hash)
    check("frontend backup retained",bool(list((root/"opt/opencode/backups").iterdir())))
    check("custom username rendered", read_env(credential)["OPENCODE_SERVER_USERNAME"] == env["OPENCODE_WEB_USER"])
    password_hash = (root/"etc/opencode/htpasswd").read_text().split(":", 1)[1].strip()
    recomputed = subprocess.check_output(["openssl","passwd","-6","-salt",password_hash.split("$")[2],"-stdin"], input=env["OPENCODE_WEB_PASSWORD"].encode()).decode().strip()
    check("nginx hash matches special-character password", recomputed == password_hash)
    binary=root/"opt/opencode/bin/opencode"
    check("native AMD64 official version",subprocess.check_output([str(binary),"--version"],text=True).strip()=="1.19.5")
    values=read_env(credential)
    native_env={**os.environ,**values,"HOME":str(root/"var/lib/opencode"),"XDG_DATA_HOME":str(root/"var/lib/opencode/data"),"XDG_CONFIG_HOME":str(root/"var/lib/opencode/config"),"XDG_CACHE_HOME":str(root/"var/cache/opencode"),"XDG_STATE_HOME":str(root/"var/lib/opencode/state"),"OPENCODE_CONFIG":str(root/"etc/opencode/opencode.json"),"OPENCODE_DISABLE_MODELS_FETCH":"1"}
    native_env.pop("OPENCODE_API_KEY",None)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    token=base64.b64encode((values["OPENCODE_SERVER_USERNAME"]+":"+values["OPENCODE_SERVER_PASSWORD"]).encode()).decode()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (root/"backend-smoke.log").open("wb") as log:
        process=subprocess.Popen([str(binary),"serve","--hostname","127.0.0.1","--port",str(port)],env=native_env,cwd=root/"var/lib/opencode/workspace",stdout=log,stderr=log)
        try:
            for attempt in range(80):
                try:
                    request=urllib.request.Request(f"http://127.0.0.1:{port}/global/health",headers={"Authorization":"Basic "+token})
                    with opener.open(request,timeout=3) as response:health=json.load(response)
                    if health.get("healthy"):break
                except OSError:time.sleep(0.25)
            else:raise AssertionError("native backend authenticated startup failed (log not printed)")
            check("native AMD64 authenticated health",health.get("version")=="1.19.5")
            try:
                opener.open(f"http://127.0.0.1:{port}/path",timeout=3)
                raise AssertionError("native backend unauthenticated API exposed")
            except urllib.error.HTTPError as error:check("native backend unauthenticated API is 401",error.code==401)
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    provider = root/"etc/opencode/provider.env"
    provider.write_text("OPENCODE_API_KEY=test-provider-placeholder\n"); provider.chmod(0o600)
    before_provider = provider.read_bytes()
    env.update(OPENCODE_WEB_USER="rotated-admin", OPENCODE_WEB_PASSWORD="rotated-test-only-password")
    install()
    check("reinstall rotates selected credentials", read_env(credential)["OPENCODE_SERVER_USERNAME"] == env["OPENCODE_WEB_USER"] and read_env(credential)["OPENCODE_SERVER_PASSWORD"] == env["OPENCODE_WEB_PASSWORD"])
    check("provider secret preserved when rotating login", provider.read_bytes() == before_provider and provider.stat().st_mode & 0o777 == 0o600)
    check("certificate preserved when rotating login", hashlib.sha256((root/"etc/opencode/tls/cert.pem").read_bytes()).hexdigest() == cert_hash)
    secret_hash = hashlib.sha256(credential.read_bytes()).hexdigest()
    subprocess.run(["bash",str(here/"uninstall.sh"),"--yes","--keep-data"],env=env,check=True,stdout=subprocess.DEVNULL)
    check("--keep-data uninstall preserves data and credentials",credential.exists() and (root/"var/lib/opencode").exists())
    check("--keep-data uninstall retains remote MCP and global fallback rules", "keenable_search" in json.loads(config_path.read_text())["mcp"] and (root/"etc/opencode/IMAGE_SEARCH.md").exists())
    check("uninstall removes binaries, units and short command",not (root/"opt/opencode").exists() and not (root/"etc/systemd/system/opencode.service").exists() and not short.exists())
    install()
    check("reinstall preserves password",hashlib.sha256(credential.read_bytes()).hexdigest()==secret_hash)
    check("reinstall restores short command",short.is_file())
    # Default (no --keep-data) = complete removal, run through the installed short command.
    subprocess.run(["bash",str(short),"--yes"],env=env,check=True,stdout=subprocess.DEVNULL)
    check("default uninstall removes everything incl. itself",not short.exists() and not any((root/d).exists() for d in ("opt/opencode","etc/opencode","var/lib/opencode","var/lib/opencode-web","var/lib/opencode-auth","var/lib/opencode-images","var/cache/opencode")))
    check("default uninstall removes Keenable config and fallback rules", not config_path.exists() and not (root/"etc/opencode/IMAGE_SEARCH.md").exists())
    check("default uninstall removes app data/credentials",not (root/"etc/opencode").exists() and not (root/"var/lib/opencode").exists())
    bad=pathlib.Path(temp)/"bad.tar.gz"
    with tarfile.open(bad,"w:gz") as tf:
        member=tarfile.TarInfo("../escaped");member.size=1;tf.addfile(member,io.BytesIO(b"x"))
    result=subprocess.run(["python3",str(here/"extract.py"),str(bad),str(pathlib.Path(temp)/"out")],capture_output=True)
    check("archive traversal rejected",result.returncode!=0 and not (pathlib.Path(temp)/"escaped").exists())
for arch,libc,expected in [("aarch64","glibc","arm64"),("aarch64","musl","arm64-musl"),("x86_64","glibc","x64-baseline"),("x86_64","musl","x64-baseline-musl")]:
    output=subprocess.check_output(["bash","-c",'source "$1/common.sh"; asset_name "$2" "$3"',"test",str(here),arch,libc],text=True).strip()
    check("asset selection "+arch+"/"+libc,output=="opencode-linux-"+expected+".tar.gz")
pathlib.Path(args.report).write_text(json.dumps({"checks":checks,"count":len(checks),"architecture":"x86_64","systemdInstall":"staged only; actual official backend process health/auth tested","modelCalls":0},indent=2)+"\n")
print(str(len(checks))+" deployment checks passed, including actual official AMD64 serve health/auth; no model calls.")
