#!/usr/bin/env bash
# Ubuntu/Debian systemd deployment; never changes octo or the main nginx service.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
host='' port=8558 backend_port=4096 workspace=/var/lib/opencode/workspace
frontend='' frontend_sha='' backend='' replace_demo=0 no_firewall=0 dry_run=0
while (($#)); do
  case "$1" in
    --host) host=${2:?}; shift 2 ;;
    --port) port=${2:?}; shift 2 ;;
    --backend-port) backend_port=${2:?}; shift 2 ;;
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
[[ "$host" =~ ^[A-Za-z0-9.:_-]+$ ]] || fail '--host is required (IP or hostname, no scheme/path)'
if ! validate_port "$port" || ! validate_port "$backend_port"; then fail 'Invalid nonprivileged port'; fi
[[ "$port" != "$backend_port" ]] || fail 'Public and internal ports must differ'
for candidate in "$port" "$backend_port"; do
  case "$candidate" in 8557|8088|8090) fail 'Refusing reserved octo ports' ;; esac
done
[[ "$workspace" =~ ^/[A-Za-z0-9_./-]+$ && "$workspace" != *..* ]] || fail 'Use a simple absolute workspace path without .. or spaces'
[[ "$frontend_sha" =~ ^[a-fA-F0-9]{64}$ ]] || fail '--frontend-sha256 is required'
[[ -f "$frontend" ]] || fail '--frontend-archive must name a local verified release tarball'
case "$workspace" in /home|/home/*|/root|/root/*) fail 'The service protects /home and /root; use an isolated /var/lib/opencode or /srv workspace' ;; esac
asset=$(asset_name "${OPENCODE_ARCH:-$(uname -m)}" "${OPENCODE_LIBC:-auto}")
expected=$(awk -v name="$asset" '$2 == name {print $1}' "$HERE/official-v1.19.5.sha256")
[[ -n "$expected" ]] || fail 'No pinned checksum for selected backend'
printf 'Pinned backend: %s (%s); HTTPS :%s -> 127.0.0.1:%s; workspace %s\n' "$VERSION" "$asset" "$port" "$backend_port" "$workspace"
if ((dry_run)); then exit 0; fi
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
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl python3 openssl nginx tar iproute2
  fi
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
printf '%s  %s\n' "$frontend_sha" "$frontend" | sha256sum -c - >/dev/null
if [[ -z "$backend" ]]; then
  backend="$tmp/$asset"
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 300 "https://github.com/anomalyco/opencode/releases/download/v$VERSION/$asset" --output "$backend"
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
mv "$(path /opt/opencode/bin/opencode.new)" "$(path /opt/opencode/bin/opencode)"
if [[ -d "$(path /opt/opencode/frontend)" ]]; then
  mv "$(path /opt/opencode/frontend)" "$(path /opt/opencode/backups)/frontend-$(date +%Y%m%d-%H%M%S)-$$"
fi
mv "$tmp/frontend" "$(path /opt/opencode/frontend)"
python3 "$HERE/render.py" "$ROOT" "$host" "$port" "$backend_port" "$workspace"
if [[ -n "$ROOT" ]]; then
  mkdir -p "$(path /var/lib/opencode/workspace)"
  printf 'Staged files only under %s; no users, services or firewall modified.\n' "$ROOT"
  exit 0
fi
for user in opencode opencode-web; do
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
chown -R opencode:opencode /var/lib/opencode /var/cache/opencode
chown -R opencode-web:opencode-web /var/lib/opencode-web
chmod 750 /var/lib/opencode /var/cache/opencode /var/lib/opencode-web
if [[ ! -d "$workspace" ]]; then
  [[ "$workspace" == /var/lib/opencode/* ]] || fail 'External workspace must already exist; installer never chowns another app workspace'
  install -d -o opencode -g opencode -m 750 "$workspace"
fi
runuser -u opencode -- test -w "$workspace" || fail 'Workspace is not writable by opencode; no external ownership was changed'
installed_version=$(runuser -u opencode -- /opt/opencode/bin/opencode --version)
[[ "$installed_version" == "$VERSION" ]] || fail "Unexpected backend version"
runuser -u opencode-web -- nginx -t -p /var/lib/opencode-web/ -c /etc/opencode/nginx.conf
systemctl daemon-reload
systemctl enable opencode.service opencode-web.service
systemctl restart opencode.service
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
printf 'Ready: https://%s:%s/ ; login username opencode. Password: /etc/opencode/server.env (root-only); Go key: /etc/opencode/provider.env. No generation performed.\n' "$host" "$port"
