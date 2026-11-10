#!/usr/bin/env python3
"""Render isolated system services. Secret values are never printed or passed in argv."""
import json, pathlib, subprocess, sys
from credentials import atomic_write, read_env, validate, write_env
from tls import ensure_certificate
from image_config import install as install_image_search
from delivery_config import install as install_delivery_rule
VERSION = "2.2.1"
# Per-model output caps (official v2 `providers` config). Lower model limits still win.
OUTPUT_LIMITS = {"opencode-go": {"deepseek-v4.1-flash": 131072}}
root, host, port, backend_port, workspace, login_file, cert_days, auth_port = sys.argv[1:]
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
config_file = p("/etc/opencode/opencode.json")
config_mode = config_file.stat().st_mode & 0o777 if config_file.exists() else 0o644
config = json.loads(config_file.read_text()) if config_file.exists() else {"$schema":"https://opencode.ai/config.json", "autoupdate":False}
# Older releases wrote an opencode-go-only whitelist, which silently hid every provider the user
# adds in the UI (custom OpenAI-compatible endpoints included). Drop only that exact value.
if config.get("enabled_providers") == ["opencode-go"]:
    del config["enabled_providers"]
# v2 reads model overrides from `providers` (the v1 `provider` key is migrated, but a bare limit override there is
# dropped). Only fill a cap the user has not set themselves.
providers = config.setdefault("providers", {})
for provider_id, models in OUTPUT_LIMITS.items():
    provider_models = providers.setdefault(provider_id, {}).setdefault("models", {})
    for model_id, output in models.items():
        limit = provider_models.setdefault(model_id, {}).setdefault("limit", {})
        limit.setdefault("output", output)
config["permission"] = {key: "allow" for key in ("*", "read", "edit", "glob", "grep", "list", "bash", "task", "external_directory", "todowrite", "question", "webfetch", "websearch", "lsp", "doom_loop", "skill")}
write("/etc/opencode/opencode.json", json.dumps(config, indent=2)+"\n", config_mode)
install_image_search(root,host,port)
install_delivery_rule(root, workspace)
ensure_certificate(p("/etc/opencode/tls"), p("/opt/opencode/backups"), host, int(cert_days))
backend = f"""[Unit]
Description=Official OpenCode {VERSION} backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory={workspace}
Environment=HOME=/var/lib/opencode XDG_DATA_HOME=/var/lib/opencode/data XDG_CONFIG_HOME=/var/lib/opencode/config XDG_CACHE_HOME=/var/cache/opencode XDG_STATE_HOME=/var/lib/opencode/state OPENCODE_CONFIG=/etc/opencode/opencode.json
EnvironmentFile=/etc/opencode/server.env
EnvironmentFile=-/etc/opencode/provider.env
ExecStart=/opt/opencode/bin/opencode serve --hostname 127.0.0.1 --port {backend_port}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=false
PrivateTmp=false
ProtectSystem=false
ProtectHome=false
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
After=network-online.target opencode.service opencode-auth.service
Wants=opencode.service opencode-auth.service

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
write("/etc/systemd/system/opencode-auth.service", f"""[Unit]
Description=OpenCode one-year cookie login gate and workspace files (browse, download, delete)
After=network.target

[Service]
Type=simple
User=opencode-auth
Group=opencode-auth
EnvironmentFile=/etc/opencode/server.env
Environment=OPENCODE_PUBLIC_ORIGIN=https://{host}:{port} OPENCODE_AUTH_PORT={auth_port} OPENCODE_AUTH_STATE=/var/lib/opencode-auth OPENCODE_WORKSPACE={workspace}
ExecStart=/usr/bin/python3 /opt/opencode/deploy/auth.py
Restart=on-failure
RestartSec=2
UMask=0077
# The root backend writes workspace files as root 0600. Download needs CAP_DAC_READ_SEARCH;
# deleting them (the only write, via unlinkat/rmdir on directory fds) needs CAP_DAC_OVERRIDE.
# No chown, setuid or other capability. Their reach is cut to the workspace by the mount
# namespace below: /var and every home directory are replaced by empty tmpfs, then only the
# workspace and the sidecar's own state are bound back; the rest of the system is read-only
# and credentials, keys and shadow files are inaccessible.
CapabilityBoundingSet=CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE
AmbientCapabilities=CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=tmpfs
TemporaryFileSystem=/var:ro
BindPaths=/var/lib/opencode-auth {workspace}
InaccessiblePaths=-/etc/opencode -/etc/shadow -/etc/shadow- -/etc/gshadow -/etc/gshadow- -/etc/ssh -/etc/sudoers -/etc/sudoers.d -/etc/ssl/private -/etc/letsencrypt -/opt/opencode/backups -/opt/opencode/bin -/boot -/srv -/mnt -/media -/run/credentials
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true
MemoryMax=96M
TasksMax=64

[Install]
WantedBy=multi-user.target
""")
write("/etc/systemd/system/opencode-image-cleanup.service", """[Unit]
Description=Remove OpenCode downloaded image cache older than seven days

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /opt/opencode/deploy/cleanup_images.py
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/opencode-images
""")
write("/etc/systemd/system/opencode-image-cleanup.timer", """[Unit]
Description=Daily OpenCode image cache expiry

[Timer]
OnCalendar=daily
RandomizedDelaySec=15m
Persistent=true
Unit=opencode-image-cleanup.service

[Install]
WantedBy=timers.target
""")
p("/var/lib/opencode-auth").mkdir(parents=True, exist_ok=True)
p("/var/lib/opencode-auth").chmod(0o700)
# opencode v2 serves its whole HTTP/RPC/SSE/WebSocket API under /api.
api = "api"
# nginx inherits add_header only when a location defines none of its own.
# Reuse the complete set, including CSP and Basic-to-cookie upgrade, at both scopes.
def response_headers(referrer):
    return f"""  add_header Set-Cookie $opencode_session_cookie always;
  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy {referrer} always;
  add_header X-Frame-Options DENY always;
  add_header Cache-Control no-store always;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; font-src 'self' data:; worker-src 'self' blob:; child-src 'self' blob:; connect-src 'self' blob: WSORIGIN; frame-ancestors 'none'" always;"""
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
  auth_request /_opencode_auth;
  auth_request_set $opencode_authorization $upstream_http_x_opencode_authorization;
  auth_request_set $opencode_session_cookie $upstream_http_set_cookie;
  error_page 497 =308 https://$host:$server_port$request_uri;
  client_max_body_size 50m;
  root /opt/opencode/frontend;
SERVER_HEADERS
  location = /_opencode_auth {
   internal;
   auth_request off;
   proxy_pass http://127.0.0.1:AUTH/auth;
   proxy_pass_request_body off;
   proxy_set_header Content-Length "";
   proxy_set_header Cookie $http_cookie;
   proxy_set_header Authorization $http_authorization;
   proxy_set_header X-Original-URI $request_uri;
   proxy_set_header X-Original-Accept $http_accept;
   proxy_set_header X-Original-Origin $http_origin;
  }
  location ~ ^/(login|logout)$ {
LOGIN_HEADERS
   auth_request off;
   proxy_pass http://127.0.0.1:AUTH;
   proxy_set_header X-Original-URI $request_uri;
   proxy_set_header X-Original-Origin $http_origin;
  }
  location = /image-preview { return 410; }
  # Authenticated (server-level auth_request + sidecar re-check) workspace browser. /files/delete is POST-only and
  # the sidecar also requires the exact Origin, a custom header and a JSON body.
  location ~ ^/files/(list|download|info|delete)$ {
   client_max_body_size 8k;
   proxy_pass http://127.0.0.1:AUTH;
   proxy_http_version 1.1;
   proxy_set_header Cookie $http_cookie;
   proxy_set_header Authorization $http_authorization;
   proxy_buffering off;
   proxy_max_temp_file_size 0;
   proxy_read_timeout 3600s;
   proxy_send_timeout 3600s;
   proxy_hide_header X-Content-Type-Options;
   proxy_hide_header Cache-Control;
   proxy_hide_header X-Frame-Options;
   proxy_hide_header Referrer-Policy;
  }
  location /files/ { return 404; }
  location ~ ^/chat-images/([a-f0-9]+[.]jpg)$ {
   alias /var/lib/opencode-images/$1;
  }
  location /chat-images/ { return 404; }
  location = /site.webmanifest { auth_request off; default_type application/manifest+json; try_files $uri =404; }
  location ~ ^/(favicon[^/]*|apple-touch-icon[^/]*|android-chrome[^/]*|web-app-manifest[^/]*)$ {
   auth_request off;
   try_files $uri =404;
  }
  location ~ ^/(API)(/|$) {
   proxy_pass http://127.0.0.1:BACKEND;
   proxy_http_version 1.1;
   proxy_set_header Host $http_host;
   proxy_set_header Authorization $opencode_authorization;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection $connection_upgrade;
   proxy_buffering off;
   proxy_request_buffering off;
   proxy_read_timeout 3600s;
   proxy_send_timeout 3600s;
  }
  location /assets/ { auth_request off; try_files $uri =404; }
  location /_assets/ { auth_request off; try_files $uri =404; }
  # No offline service worker behind the login gate (the app also unregisters old ones).
  location = /sw.js { return 404; }
  location / { error_page 401 = /login; try_files $uri /index.html; }
 }
}
"""
write("/etc/opencode/nginx.conf", nginx.replace("SERVER_HEADERS", response_headers("no-referrer")).replace("LOGIN_HEADERS", response_headers("same-origin")).replace("WSORIGIN", "wss://" + ("["+host+"]" if ":" in host else host) + ":" + port).replace("PORT",port).replace("HOST",host).replace("BACKEND",backend_port).replace("AUTH",auth_port).replace("API",api))
write("/etc/opencode/install.json", json.dumps({"version":VERSION,"host":host,"port":int(port),"backend_port":int(backend_port),"auth_port":int(auth_port),"workspace":workspace},indent=2)+"\n")
