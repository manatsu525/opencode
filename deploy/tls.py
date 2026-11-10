#!/usr/bin/env python3
"""Isolated ten-year self-signed TLS; preserve long-lived pairs, back up short ones."""
import datetime, ipaddress, os, pathlib, shutil, subprocess, tempfile

CERT_DAYS = 3650
RENEW_BEFORE_DAYS = 9 * 365

def ensure_certificate(folder, backups, host, days=CERT_DAYS):
    folder, backups = pathlib.Path(folder), pathlib.Path(backups)
    folder.mkdir(parents=True, exist_ok=True)
    cert, key = folder / "cert.pem", folder / "key.pem"
    if cert.exists() != key.exists(): raise SystemExit("Incomplete TLS certificate/key pair")
    if cert.exists():
        status = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-checkend", str(RENEW_BEFORE_DAYS * 86400)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if status.returncode == 0:
            key.chmod(0o640); cert.chmod(0o644)
            return False
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
        backup = pathlib.Path(tempfile.mkdtemp(prefix="tls-" + stamp + "-", dir=str(backups)))
        for file in (cert, key): shutil.copy2(file, backup / file.name)
    try: ipaddress.ip_address(host); san = "IP:" + host
    except ValueError: san = "DNS:" + host
    with tempfile.TemporaryDirectory(prefix=".tls-", dir=str(folder)) as temp:
        c, k = pathlib.Path(temp) / "cert.pem", pathlib.Path(temp) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-days", str(days), "-nodes", "-subj", "/CN=" + host, "-addext", "subjectAltName=" + san, "-keyout", str(k), "-out", str(c)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if key.exists() and os.geteuid() == 0: os.chown(k, 0, key.stat().st_gid)
        k.chmod(0o640); c.chmod(0o644)
        k.replace(key); c.replace(cert)
    return True
