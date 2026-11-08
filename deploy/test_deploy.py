#!/usr/bin/env python3
"""Safe AMD64 staging/idempotence/purge and native backend smoke test (no system changes)."""
import argparse, base64, hashlib, io, json, os, pathlib, socket, subprocess, tarfile, tempfile, time, urllib.error, urllib.request
parser=argparse.ArgumentParser();parser.add_argument("--frontend",required=True);parser.add_argument("--backend",required=True);parser.add_argument("--report",required=True);args=parser.parse_args()
here=pathlib.Path(__file__).resolve().parent
sha=hashlib.sha256(pathlib.Path(args.frontend).read_bytes()).hexdigest()
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append(name)
with tempfile.TemporaryDirectory(prefix="opencode-deploy-test-") as temp:
    root=pathlib.Path(temp)/"root";root.mkdir()
    env={**os.environ,"DESTDIR":str(root),"OPENCODE_ARCH":"x86_64","OPENCODE_LIBC":"glibc"}
    command=["bash",str(here/"install.sh"),"--host","127.0.0.1","--frontend-archive",str(pathlib.Path(args.frontend).resolve()),"--frontend-sha256",sha,"--backend-archive",str(pathlib.Path(args.backend).resolve())]
    def install():subprocess.run(command,env=env,check=True,stdout=subprocess.DEVNULL)
    install()
    check("installer/uninstaller retained",(root/"opt/opencode/deploy/uninstall.sh").is_file())
    credential=root/"etc/opencode/server.env";secret_hash=hashlib.sha256(credential.read_bytes()).hexdigest();cert_hash=hashlib.sha256((root/"etc/opencode/tls/cert.pem").read_bytes()).hexdigest()
    check("root-only credential mode",credential.stat().st_mode&0o777==0o600)
    check("web unit is unprivileged","User=opencode-web" in (root/"etc/systemd/system/opencode-web.service").read_text())
    install()
    check("idempotent server password",hashlib.sha256(credential.read_bytes()).hexdigest()==secret_hash)
    check("idempotent certificate",hashlib.sha256((root/"etc/opencode/tls/cert.pem").read_bytes()).hexdigest()==cert_hash)
    check("frontend backup retained",bool(list((root/"opt/opencode/backups").iterdir())))
    binary=root/"opt/opencode/bin/opencode"
    check("native AMD64 official version",subprocess.check_output([str(binary),"--version"],text=True).strip()=="1.19.5")
    values=dict(line.split("=",1) for line in credential.read_text().splitlines() if "=" in line)
    native_env={**os.environ,**values,"HOME":str(root/"var/lib/opencode"),"XDG_DATA_HOME":str(root/"var/lib/opencode/data"),"XDG_CONFIG_HOME":str(root/"var/lib/opencode/config"),"XDG_CACHE_HOME":str(root/"var/cache/opencode"),"XDG_STATE_HOME":str(root/"var/lib/opencode/state"),"OPENCODE_CONFIG":str(root/"etc/opencode/opencode.json"),"OPENCODE_DISABLE_MODELS_FETCH":"1"}
    native_env.pop("OPENCODE_API_KEY",None)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    token=base64.b64encode(("opencode:"+values["OPENCODE_SERVER_PASSWORD"]).encode()).decode()
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
    subprocess.run(["bash",str(here/"uninstall.sh"),"--yes"],env=env,check=True,stdout=subprocess.DEVNULL)
    check("default uninstall preserves data and credentials",credential.exists() and (root/"var/lib/opencode").exists())
    check("uninstall removes binaries and units",not (root/"opt/opencode").exists() and not (root/"etc/systemd/system/opencode.service").exists())
    install()
    check("reinstall preserves password",hashlib.sha256(credential.read_bytes()).hexdigest()==secret_hash)
    subprocess.run(["bash",str(here/"uninstall.sh"),"--yes","--purge"],env=env,check=True,stdout=subprocess.DEVNULL)
    check("purge removes app data/credentials",not (root/"etc/opencode").exists() and not (root/"var/lib/opencode").exists())
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
