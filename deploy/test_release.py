#!/usr/bin/env python3
"""Verified one-click bootstrap/default downloads, corrupt assets, and TLS renewal."""
import argparse, functools, hashlib, http.server, json, os, pathlib, pty, select, signal, socketserver, subprocess, sys, tarfile, tempfile, threading, time
from credentials import read_env
from tls import CERT_DAYS, RENEW_BEFORE_DAYS, ensure_certificate

parser=argparse.ArgumentParser();parser.add_argument('--frontend',required=True);parser.add_argument('--backend',required=True);parser.add_argument('--arch',default=os.uname().machine);args=parser.parse_args()
here=pathlib.Path(__file__).resolve().parent
checks=[]
def check(name, condition):
    if not condition:raise AssertionError(name)
    checks.append(name)
def checksum(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def sidecar(file):file.with_name(file.name+'.sha256').write_text(checksum(file)+'  '+file.name+'\n')
def tty_run(command, steps, env):
    pid,fd=pty.fork()
    if pid==0:os.execvpe(command[0],command,env)
    output=bytearray();pending=bytearray()
    try:
        for marker,value in steps:
            deadline=time.monotonic()+75
            while marker not in pending:
                left=deadline-time.monotonic()
                if left<=0 or not select.select([fd],[],[],left)[0]:raise AssertionError('Missing TTY prompt '+marker.decode())
                try:chunk=os.read(fd,65536)
                except OSError:chunk=b''
                if not chunk:raise AssertionError('Installer stopped before TTY prompt '+marker.decode())
                output.extend(chunk);pending.extend(chunk)
            del pending[:pending.index(marker)+len(marker)]
            os.write(fd,value+b'\n')
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            done,status=os.waitpid(pid,os.WNOHANG)
            if done:
                pid=None
                check('piped one-click installer exits successfully',os.WIFEXITED(status) and os.WEXITSTATUS(status)==0)
                return bytes(output)
            if select.select([fd],[],[],0.1)[0]:
                try:output.extend(os.read(fd,65536))
                except OSError:pass
        raise AssertionError('Installer completion timeout')
    finally:
        os.close(fd)
        if pid is not None:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)

with tempfile.TemporaryDirectory(prefix='opencode-release-test-') as temp:
    root=pathlib.Path(temp);fixtures=root/'fixtures';fixtures.mkdir();work=root/'work';work.mkdir()
    bundle=fixtures/'opencode-deploy-v2.2.1-manatsu.3.tar.gz'
    with tarfile.open(bundle,'w:gz') as archive:
        archive.add(here,arcname='deploy',filter=lambda member:None if '__pycache__' in member.name else member)
    sidecar(bundle)
    frontend=fixtures/'opencode-web-v2.2.1-manatsu.3.tar.gz';frontend.symlink_to(pathlib.Path(args.frontend).resolve());sidecar(frontend)
    asset=subprocess.check_output(['bash','-c','source "$1/common.sh"; asset_name "$2" glibc','test',str(here),args.arch],text=True).strip()
    (fixtures/asset).symlink_to(pathlib.Path(args.backend).resolve())
    (fixtures/'install.sh').write_bytes((here/'install.sh').read_bytes())
    requests=[]
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):requests.append(self.path);super().do_GET()
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(fixtures)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url='http://127.0.0.1:'+str(server.server_address[1])
        env={key:value for key,value in os.environ.items() if key not in ('OPENCODE_DEPLOY_DIR','OPENCODE_WEB_HOST','OPENCODE_WEB_USER','OPENCODE_WEB_PASSWORD')}
        stage=root/'stage'
        env.update(DESTDIR=str(stage),TMPDIR=str(work),OPENCODE_RELEASE_BASE_URL=url,OPENCODE_BACKEND_BASE_URL=url,OPENCODE_ARCH=args.arch,OPENCODE_LIBC='glibc')
        piped=['bash','-c','set -o pipefail; curl -fsSL "$1/install.sh" | bash','test',url]
        secret=b'One-click-fake-test-password'
        output=tty_run(piped,[(b'Public IP or domain for HTTPS (required): ',b'127.0.0.1'),(b'Login username [admin]: ',b''),(b'Login password (required): ',secret),(b'Confirm password: ',secret)],env)
        values=read_env(stage/'etc/opencode/server.env')
        check('no-argument one-click prompts for host/admin/password',values['OPENCODE_SERVER_USERNAME']=='admin' and values['OPENCODE_SERVER_PASSWORD']==secret.decode())
        check('one-click never echoes hidden password',secret not in output)
        check('default deploy/frontend/checksum/backend downloads requested',all('/'+name in requests for name in (bundle.name,bundle.name+'.sha256',frontend.name,frontend.name+'.sha256',asset)))
        check('bootstrap and credential temporary directories cleaned',not list(work.iterdir()))
        cert=stage/'etc/opencode/tls/cert.pem'
        check('fresh install certificate is ten years',subprocess.run(['openssl','x509','-in',str(cert),'-noout','-checkend',str((CERT_DAYS-1)*86400)],capture_output=True).returncode==0)
        auth_env={**env,'OPENCODE_WEB_HOST':'127.0.0.1','OPENCODE_WEB_USER':'test-admin','OPENCODE_WEB_PASSWORD':'fake-test-automation-secret'}
        frontend.with_name(frontend.name+'.sha256').write_text('0'*64+'  '+frontend.name+'\n')
        bad=root/'bad-frontend';result=subprocess.run(['bash'],input=(here/'install.sh').read_bytes(),env={**auth_env,'DESTDIR':str(bad)},capture_output=True,start_new_session=True)
        check('corrupt default frontend rejected before live state changes',result.returncode!=0 and not (bad/'etc/opencode/server.env').exists())
        sidecar(frontend)
        bundle.with_name(bundle.name+'.sha256').write_text('0'*64+'  '+bundle.name+'\n')
        bad=root/'bad-bootstrap';result=subprocess.run(['bash'],input=(here/'install.sh').read_bytes(),env={**auth_env,'DESTDIR':str(bad)},capture_output=True,start_new_session=True)
        check('corrupt bootstrap rejected before execution',result.returncode!=0 and not bad.exists())
        sidecar(bundle)
        check('failure paths remove temporary files',not list(work.iterdir()))
    finally:server.shutdown();server.server_close();thread.join()
    tls=root/'tls';backup=root/'tls-backups';tls.mkdir()
    check('default certificate days and renewal threshold',CERT_DAYS==3650 and RENEW_BEFORE_DAYS==3285)
    ensure_certificate(tls,backup,'127.0.0.1')
    old=[(tls/name).read_bytes() for name in ('cert.pem','key.pem')]
    check('long-lived certificate and key kept on reinstall',ensure_certificate(tls,backup,'127.0.0.1') is False and old==[(tls/name).read_bytes() for name in ('cert.pem','key.pem')])
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','825','-subj','/CN=127.0.0.1','-keyout',str(tls/'key.pem'),'-out',str(tls/'cert.pem')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    short=[(tls/name).read_bytes() for name in ('cert.pem','key.pem')]
    check('certificate expiring in less than nine years renewed',ensure_certificate(tls,backup,'127.0.0.1') is True and short!=[(tls/name).read_bytes() for name in ('cert.pem','key.pem')])
    saves=list(backup.iterdir())
    check('old certificate and key backed up privately',len(saves)==1 and saves[0].stat().st_mode&0o777==0o700 and short==[(saves[0]/name).read_bytes() for name in ('cert.pem','key.pem')])
    check('replacement lasts 3650 days',subprocess.run(['openssl','x509','-in',str(tls/'cert.pem'),'-noout','-checkend',str((CERT_DAYS-1)*86400)],capture_output=True).returncode==0)
print(str(len(checks))+' release/bootstrap/TLS checks passed; no model calls.')
