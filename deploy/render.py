#!/usr/bin/env python3
"""Render isolated system services. Secret values are never printed or passed in argv."""
import json, pathlib, subprocess, sys
from credentials import atomic_write, read_env, validate, write_env
from tls import ensure_certificate
VERSION = "1.19.5"
root, host, port, backend_port, workspace, login_file, cert_days = sys.argv[1:]
def p(name): return pathlib.Path(root + name)
def write(name, value, mode=0o644):
    file = p(name); file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(value); file.chmod(mode)
for folder in ["/etc/opencode", "/etc/opencode/tls", "/var/lib/opencode", "/var/cache/opencode", "/var/lib/opencode-web", "/var/lib/opencode-web/client", "/var/lib/opencode-web/proxy"]:
    p(folder).mkdir(parents=True, exist_ok=True)
p("/etc/opencode").chmod(0o755)
p("/etc/opencode/tls").chmod(0o750)
server = p("/etc/opencode/server.env")
login = json.loads(pathlib.Path(login_file).read_text())
username, password = login["username"], login["password"]
validate(username, password)
values = read_env(server)
values.update(OPENCODE_SERVER_USERNAME=username, OPENCODE_SERVER_PASSWORD=password, OPENCODE_DISABLE_AUTOUPDATE="1")
write_env(server, values)
hashed = subprocess.check_output(["openssl", "passwd", "-6", "-stdin"], input=password.encode()).decode().strip()
atomic_write(p("/etc/opencode/htpasswd"), username + ":" + hashed + "\n", 0o640)
if not p("/etc/opencode/provider.env").exists():
    write("/etc/opencode/provider.env", "# Add your real OpenCode Go key here, then restart opencode.\n# OPENCODE_API_KEY=\n", 0o600)
if not p("/etc/opencode/opencode.json").exists():
    write("/etc/opencode/opencode.json", json.dumps({"$schema":"https://opencode.ai/config.json", "autoupdate":False, "enabled_providers":["opencode-go"]}, indent=2)+"\n")
ensure_certificate(p("/etc/opencode/tls"), p("/opt/opencode/backups"), host, int(cert_days))
backend = f"""[Unit]
Description=Official OpenCode {VERSION} backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opencode
Group=opencode
WorkingDirectory={workspace}
Environment=HOME=/var/lib/opencode XDG_DATA_HOME=/var/lib/opencode/data XDG_CONFIG_HOME=/var/lib/opencode/config XDG_CACHE_HOME=/var/cache/opencode XDG_STATE_HOME=/var/lib/opencode/state OPENCODE_CONFIG=/etc/opencode/opencode.json
EnvironmentFile=/etc/opencode/server.env
EnvironmentFile=-/etc/opencode/provider.env
ExecStart=/opt/opencode/bin/opencode serve --hostname 127.0.0.1 --port {backend_port}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/opencode /var/cache/opencode {workspace}
MemoryHigh=768M
MemoryMax=1536M
CPUQuota=150%
TasksMax=256
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""
write("/etc/systemd/system/opencode.service", backend)
write("/etc/systemd/system/opencode-web.service", """[Unit]
Description=Custom OpenCode HTTPS frontend (isolated nginx)
After=network-online.target opencode.service
Wants=opencode.service

[Service]
Type=simple
User=opencode-web
Group=opencode-web
ExecStartPre=/usr/sbin/nginx -t -p /var/lib/opencode-web/ -c /etc/opencode/nginx.conf
ExecStart=/usr/sbin/nginx -p /var/lib/opencode-web/ -c /etc/opencode/nginx.conf -g 'daemon off;'
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=3
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/opencode-web
MemoryMax=128M
CPUQuota=50%
TasksMax=32

[Install]
WantedBy=multi-user.target
""")
api = "agent|api|auth|command|config|doc|event|experimental|file|find|formatter|global|instance|log|lsp|mcp|path|permission|project|provider|pty|question|session|skill|sync|tui|vcs"
nginx = """worker_processes 1;
pid /var/lib/opencode-web/nginx.pid;
error_log stderr warn;
events { worker_connections 256; }
http {
 include /etc/nginx/mime.types;
 default_type application/octet-stream;
 log_format safe '$time_iso8601 $remote_addr $request_method $uri $status';
 access_log /var/lib/opencode-web/access.log safe;
 client_body_temp_path /var/lib/opencode-web/client;
 proxy_temp_path /var/lib/opencode-web/proxy;
 map $http_upgrade $connection_upgrade { default upgrade; '' close; }
 server {
  listen 0.0.0.0:PORT ssl;
  server_name HOST;
  ssl_certificate /etc/opencode/tls/cert.pem;
  ssl_certificate_key /etc/opencode/tls/key.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_session_cache shared:OpenCodeTLS:1m;
  auth_basic "OpenCode";
  auth_basic_user_file /etc/opencode/htpasswd;
  error_page 497 =308 https://$host:$server_port$request_uri;
  client_max_body_size 50m;
  root /opt/opencode/frontend;
  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy no-referrer always;
  add_header X-Frame-Options DENY always;
  add_header Cache-Control no-store always;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; font-src 'self' data:; worker-src 'self' blob:; child-src 'self' blob:; connect-src 'self' blob: WSORIGIN; frame-ancestors 'none'" always;
  location ~ ^/(API)(/|$) {
   proxy_pass http://127.0.0.1:BACKEND;
   proxy_http_version 1.1;
   proxy_set_header Host $http_host;
   proxy_set_header Authorization $http_authorization;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection $connection_upgrade;
   proxy_buffering off;
   proxy_request_buffering off;
   proxy_read_timeout 3600s;
   proxy_send_timeout 3600s;
  }
  location /assets/ { try_files $uri =404; }
  location / { try_files $uri /index.html; }
 }
}
"""
write("/etc/opencode/nginx.conf", nginx.replace("WSORIGIN", "wss://" + ("["+host+"]" if ":" in host else host) + ":" + port).replace("PORT",port).replace("HOST",host).replace("BACKEND",backend_port).replace("API",api))
write("/etc/opencode/install.json", json.dumps({"version":VERSION,"host":host,"port":int(port),"backend_port":int(backend_port),"workspace":workspace},indent=2)+"\n")
