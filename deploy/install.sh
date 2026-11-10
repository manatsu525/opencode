#!/usr/bin/env bash
# Ubuntu/Debian systemd deployment; never changes octo or the main nginx service.
set -euo pipefail
# A piped script must not source helpers from an untrusted current directory.
RELEASE_TAG=v1.19.5-manatsu.1
RELEASE_BASE=${OPENCODE_RELEASE_BASE_URL:-https://github.com/manatsu525/opencode/releases/download/$RELEASE_TAG}
FRONTEND_ASSET=opencode-web-$RELEASE_TAG.tar.gz
DEPLOY_ASSET=opencode-deploy-$RELEASE_TAG.tar.gz
CERT_DAYS=3650
fetch() { curl --fail --silent --show-error --location --retry 3 --connect-timeout 20 --max-time 300 "$1" --output "$2"; }
checksum() {
  local digest name extra
  [[ $(wc -l < "$1") -eq 1 ]] || { printf 'Invalid release checksum file\n' >&2; return 1; }
  read -r digest name extra < "$1"
  [[ "$digest" =~ ^[a-fA-F0-9]{64}$ && "$name" == "$2" && -z "$extra" ]] || { printf 'Invalid release checksum entry\n' >&2; return 1; }
  printf '%s' "$digest"
}
install_source=${OPENCODE_DEPLOY_DIR:-}
if [[ -z "$install_source" && -n "${BASH_SOURCE[0]:-}" ]]; then
  install_source=$(dirname -- "${BASH_SOURCE[0]}")
fi
if [[ -z "$install_source" || ! -f "$install_source/common.sh" ]]; then
  if [[ -z "${DESTDIR:-}" ]]; then
    (( EUID == 0 )) || { printf 'Run the one-click installer with sudo bash\n' >&2; exit 1; }
    [[ -d /run/systemd/system ]] || { printf 'Ubuntu/Debian with running systemd is required\n' >&2; exit 1; }
    if ! command -v python3 >/dev/null || ! command -v curl >/dev/null || ! command -v tar >/dev/null; then
      apt-get update -qq
      DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-upgrade --no-install-recommends ca-certificates curl python3 tar
    fi
  fi
  bootstrap=$(mktemp -d)
  trap 'rm -rf -- "$bootstrap"' EXIT
  fetch "$RELEASE_BASE/$DEPLOY_ASSET" "$bootstrap/$DEPLOY_ASSET"
  fetch "$RELEASE_BASE/$DEPLOY_ASSET.sha256" "$bootstrap/$DEPLOY_ASSET.sha256"
  bootstrap_sha=$(checksum "$bootstrap/$DEPLOY_ASSET.sha256" "$DEPLOY_ASSET")
  printf '%s  %s\n' "$bootstrap_sha" "$bootstrap/$DEPLOY_ASSET" | sha256sum -c - >/dev/null
  # Validate member paths/types before running any code from the verified bundle.
  python3 - "$bootstrap/$DEPLOY_ASSET" "$bootstrap" <<'BOOTSTRAP_PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], "r:gz") as archive:
    members = archive.getmembers()
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "deploy" or not (member.isfile() or member.isdir()):
            raise SystemExit("Unsafe deployment bundle member")
        member.mode &= 0o755
    archive.extractall(sys.argv[2], members=members)
BOOTSTRAP_PY
  [[ -f "$bootstrap/deploy/install.sh" && -f "$bootstrap/deploy/common.sh" ]] || { printf 'Incomplete deployment bundle\n' >&2; exit 1; }
  OPENCODE_DEPLOY_DIR="$bootstrap/deploy" bash "$bootstrap/deploy/install.sh" "$@"
  exit 0
fi
# shellcheck source=common.sh
source "$install_source/common.sh"
host=${OPENCODE_WEB_HOST:-} port=8558 backend_port=4096 auth_port=4097 workspace=/var/lib/opencode/workspace
frontend='' frontend_sha='' backend='' replace_demo=0 no_firewall=0 dry_run=0
while (($#)); do
  case "$1" in
    --host) host=${2:?}; shift 2 ;;
    --port) port=${2:?}; shift 2 ;;
    --backend-port) backend_port=${2:?}; shift 2 ;;
    --auth-port) auth_port=${2:?}; shift 2 ;;
    --workspace) workspace=${2:?}; shift 2 ;;
    --frontend-archive) frontend=${2:?}; shift 2 ;;
    --frontend-sha256) frontend_sha=${2:?}; shift 2 ;;
    --backend-archive) backend=${2:?}; shift 2 ;;
    --replace-demo) replace_demo=1; shift ;;
    --no-firewall) no_firewall=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    *) fail "Unknown option: $1" ;;
  esac
done
if [[ -z "$host" ]]; then
  if ((dry_run)); then host=YOUR_IP_OR_DOMAIN
  elif ! read -r -p 'Public IP or domain for HTTPS (required): ' host </dev/tty; then
    fail 'Host input unavailable: set OPENCODE_WEB_HOST or pass --host (and supply login automation variables)'
  fi
fi
[[ "$host" =~ ^[A-Za-z0-9.:_-]+$ ]] || fail 'A public IP or hostname is required (no scheme/path)'
if ! validate_port "$port" || ! validate_port "$backend_port" || ! validate_port "$auth_port"; then fail 'Invalid nonprivileged port'; fi
[[ "$port" != "$backend_port" && "$port" != "$auth_port" && "$backend_port" != "$auth_port" ]] || fail 'Public and internal ports must differ'
for candidate in "$port" "$backend_port" "$auth_port"; do
  case "$candidate" in 8557|8088|8090) fail 'Refusing reserved octo ports' ;; esac
done
[[ "$workspace" =~ ^/[A-Za-z0-9_./-]+$ && "$workspace" != *..* ]] || fail 'Use a simple absolute workspace path without .. or spaces'
if [[ -n "$frontend" || -n "$frontend_sha" ]]; then
  [[ "$frontend_sha" =~ ^[a-fA-F0-9]{64}$ ]] || fail '--frontend-sha256 is required with a local archive'
  [[ -f "$frontend" ]] || fail '--frontend-archive must name a local verified release tarball'
fi
asset=$(asset_name "${OPENCODE_ARCH:-$(uname -m)}" "${OPENCODE_LIBC:-auto}")
expected=$(awk -v name="$asset" '$2 == name {print $1}' "$HERE/official-v1.19.5.sha256")
[[ -n "$expected" ]] || fail 'No pinned checksum for selected backend'
printf 'Pinned backend: %s (%s); HTTPS :%s -> 127.0.0.1:%s; workspace %s\n' "$VERSION" "$asset" "$port" "$backend_port" "$workspace"
if ((dry_run)); then printf 'Frontend release: %s/%s (+ .sha256); certificate: %s days\n' "$RELEASE_BASE" "$FRONTEND_ASSET" "$CERT_DAYS"; exit 0; fi
if [[ -z "$ROOT" ]]; then
  (( EUID == 0 )) || fail 'Run with sudo/root'
  if [[ ! -f /etc/opencode/install.json && ( -e /etc/systemd/system/opencode.service || -e /etc/systemd/system/opencode-web.service ) ]]; then
    fail 'Refusing to overwrite unmanaged OpenCode units'
  fi
  command -v apt-get >/dev/null || fail 'Installer requires Ubuntu/Debian with apt and systemd (musl asset selection is available separately)'
  [[ -d /run/systemd/system ]] || fail 'A running systemd host is required; DESTDIR is staging-only'
  missing=0
  for dependency in curl python3 openssl nginx tar ss runuser useradd; do
    if ! command -v "$dependency" >/dev/null; then missing=1; fi
  done
  if ((missing)); then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-upgrade --no-install-recommends ca-certificates curl python3 python3-pil openssl nginx tar iproute2
  fi
fi
# Image search downloads verified raster files; Pillow resizes and strips metadata.
if [[ -z "$ROOT" ]] && ! python3 -c 'import PIL' >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-upgrade --no-install-recommends python3-pil
fi
tmp=$(mktemp -d)
demo_stopped=0
finish() {
  local rc=$?
  rm -rf -- "$tmp"
  if (( rc != 0 && demo_stopped )); then
    systemctl stop opencode-web.service || true
    systemctl start opencode-ui-demo.service || true
    printf 'Installation failed; previous demo restarted. Inspect opencode units without exposing secrets.\n' >&2
  fi
}
trap finish EXIT
# Always collect explicit login input, before downloads or changes to the live login.
python3 "$HERE/credentials.py" "$tmp/login.json"
if [[ -z "$frontend" ]]; then
  frontend="$tmp/$FRONTEND_ASSET"
  fetch "$RELEASE_BASE/$FRONTEND_ASSET" "$frontend"
  fetch "$RELEASE_BASE/$FRONTEND_ASSET.sha256" "$frontend.sha256"
  frontend_sha=$(checksum "$frontend.sha256" "$FRONTEND_ASSET")
fi
printf '%s  %s\n' "$frontend_sha" "$frontend" | sha256sum -c - >/dev/null
if [[ -z "$backend" ]]; then
  backend="$tmp/$asset"
  fetch "${OPENCODE_BACKEND_BASE_URL:-https://github.com/anomalyco/opencode/releases/download/v$VERSION}/$asset" "$backend"
fi
[[ -f "$backend" ]] || fail 'Backend archive not found'
printf '%s  %s\n' "$expected" "$backend" | sha256sum -c - >/dev/null
python3 "$HERE/extract.py" "$backend" "$tmp/backend"
[[ -f "$tmp/backend/opencode" ]] || fail 'Official archive did not contain opencode'
python3 "$HERE/extract.py" "$frontend" "$tmp/frontend"
[[ -f "$tmp/frontend/index.html" && -d "$tmp/frontend/assets" ]] || fail 'Invalid frontend archive'
mkdir -p "$(path /opt/opencode/bin)" "$(path /opt/opencode/backups)" "$(path /opt/opencode/deploy)"
if [[ "$(realpath "$HERE")" != "$(realpath "$(path /opt/opencode/deploy)")" ]]; then
  cp -a "$HERE/." "$(path /opt/opencode/deploy)/"
fi
install -m 755 "$tmp/backend/opencode" "$(path /opt/opencode/bin/opencode.new)"
# Standalone short command for complete removal: sudo opencode-uninstall
install -d -m 755 "$(path /usr/local/bin)"
install -m 755 "$HERE/uninstall.sh" "$(path /usr/local/bin/opencode-uninstall)"
mv "$(path /opt/opencode/bin/opencode.new)" "$(path /opt/opencode/bin/opencode)"
if [[ -d "$(path /opt/opencode/frontend)" ]]; then
  mv "$(path /opt/opencode/frontend)" "$(path /opt/opencode/backups)/frontend-$(date +%Y%m%d-%H%M%S)-$$"
fi
mv "$tmp/frontend" "$(path /opt/opencode/frontend)"
# Render also merges image_search + keyless remote keenable_search and their global fallback rules.
python3 "$HERE/render.py" "$ROOT" "$host" "$port" "$backend_port" "$workspace" "$tmp/login.json" "$CERT_DAYS" "$auth_port"
if [[ -n "$ROOT" ]]; then
  mkdir -p "$(path /var/lib/opencode/workspace)"
  printf 'Staged files only under %s; no users, services or firewall modified.\n' "$ROOT"
  exit 0
fi
for user in opencode-web opencode-auth; do
  if id "$user" >/dev/null 2>&1; then
    existing_home=$(getent passwd "$user" | cut -d: -f6)
    [[ "$existing_home" == "/var/lib/$user" ]] || fail "Refusing to reuse unrelated account: $user"
  fi
  if ! id "$user" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "/var/lib/$user" --shell /usr/sbin/nologin "$user"
  fi
done
chown root:opencode-web /etc/opencode/tls /etc/opencode/tls/key.pem /etc/opencode/htpasswd
chmod 755 /etc/opencode
chmod 750 /etc/opencode/tls
chmod 640 /etc/opencode/tls/key.pem /etc/opencode/htpasswd
chown -R root:root /var/lib/opencode /var/cache/opencode
chown -R opencode-auth:opencode-auth /var/lib/opencode-auth
chmod 700 /var/lib/opencode-auth
chown -R opencode-web:opencode-web /var/lib/opencode-web
chmod 750 /var/lib/opencode /var/cache/opencode /var/lib/opencode-web
if [[ ! -d "$workspace" ]]; then
  [[ "$workspace" == /var/lib/opencode/* ]] || fail 'External workspace must already exist; installer never chowns another app workspace'
  install -d -o root -g root -m 750 "$workspace"
fi
test -w "$workspace" || fail 'Workspace is not writable by backend root; no external ownership was changed'
installed_version=$(/opt/opencode/bin/opencode --version)
[[ "$installed_version" == "$VERSION" ]] || fail "Unexpected backend version"
runuser -u opencode-web -- nginx -t -p /var/lib/opencode-web/ -c /etc/opencode/nginx.conf
systemctl daemon-reload
systemctl enable opencode.service opencode-web.service opencode-auth.service
systemctl enable --now opencode-image-cleanup.timer
systemctl restart opencode-auth.service opencode.service
python3 "$HERE/verify.py" --internal --port "$backend_port"
if systemctl is-active --quiet opencode-ui-demo.service; then
  ((replace_demo)) || fail 'Demo is active; pass --replace-demo to replace only its listener'
  [[ -e /etc/opencode/demo-was-active ]] || touch /etc/opencode/demo-was-active
  if systemctl is-enabled --quiet opencode-ui-demo.service; then
    touch /etc/opencode/demo-was-enabled
    systemctl disable opencode-ui-demo.service
  fi
  systemctl stop opencode-ui-demo.service
  demo_stopped=1
fi
if (( ! no_firewall )) && command -v iptables >/dev/null; then
  if ! iptables -C INPUT -p tcp --dport "$port" -m comment --comment opencode-ui-demo -j ACCEPT 2>/dev/null && ! iptables -C INPUT -p tcp --dport "$port" -m comment --comment opencode-web -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 1 -p tcp --dport "$port" -m comment --comment opencode-web -j ACCEPT
    printf '%s\n' "$port" >/etc/opencode/firewall-owned-port
    if systemctl is-active --quiet netfilter-persistent.service; then netfilter-persistent save; fi
  fi
fi
systemctl restart opencode-web.service
python3 "$HERE/verify.py" --port "$port"
demo_stopped=0
printf 'Ready: https://%s:%s/ ; Login credentials: /etc/opencode/server.env (root-only); Go key: /etc/opencode/provider.env. Uninstall everything: sudo opencode-uninstall. No generation performed.\n' "$host" "$port"
