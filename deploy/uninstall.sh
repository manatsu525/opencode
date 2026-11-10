#!/usr/bin/env bash
# Remove only this deployment; never remove octo, external workspaces or old demo backups.
set -euo pipefail
# Works from /opt/opencode/deploy, a checkout, or piped: curl -fsSL .../deploy/uninstall.sh | sudo bash -s -- --yes [--purge]
self=${BASH_SOURCE[0]:-}
if [[ -n "$self" && -f "$(dirname -- "$self")/common.sh" ]]; then
  # shellcheck source=common.sh
  source "$(dirname -- "$self")/common.sh"
else
  ROOT=${DESTDIR:-}
  [[ -z "$ROOT" || ( "$ROOT" == /* && "$ROOT" != / && "$ROOT" != *..* ) ]] || { printf "Invalid DESTDIR\n" >&2; exit 1; }
  path() { printf '%s%s' "$ROOT" "$1"; }
  fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
  validate_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1024 && 10#$1 <= 65535 )); }
fi
yes=0 purge=0 restore_demo=0
while (($#)); do
  case "$1" in --yes) yes=1 ;; --purge) purge=1 ;; --restore-demo) restore_demo=1 ;; *) fail "Unknown option: $1" ;; esac
  shift
done
((yes)) || fail 'Explicit --yes required; --purge permanently deletes OpenCode data/workspace and credentials'
if [[ -z "$ROOT" ]]; then
  (( EUID == 0 )) || fail 'Run with sudo/root'
  systemctl disable --now opencode-image-cleanup.timer opencode-web.service opencode-auth.service opencode.service 2>/dev/null || true
  systemctl stop opencode-image-cleanup.service 2>/dev/null || true
  if [[ -f /etc/opencode/firewall-owned-port ]]; then
    read -r port </etc/opencode/firewall-owned-port
    validate_port "$port" || fail 'Invalid owned firewall record'
    iptables -D INPUT -p tcp --dport "$port" -m comment --comment opencode-web -j ACCEPT
    if systemctl is-active --quiet netfilter-persistent.service; then netfilter-persistent save; fi
  fi
fi
rm -f -- "$(path /etc/systemd/system/opencode-image-cleanup.timer)" "$(path /etc/systemd/system/opencode-image-cleanup.service)" "$(path /etc/systemd/system/opencode.service)" "$(path /etc/systemd/system/opencode-web.service)" "$(path /etc/systemd/system/opencode-auth.service)"
rm -rf -- "$(path /opt/opencode)" "$(path /var/lib/opencode-web)"
# Remote keenable_search has no local daemon/files beyond /etc/opencode config and rules.
# Default uninstall retains MCP settings for reinstall; --purge removes them with /etc/opencode.
if ((purge)); then
  rm -rf -- "$(path /var/lib/opencode)" "$(path /var/cache/opencode)" "$(path /var/lib/opencode-auth)" "$(path /var/lib/opencode-images)" "$(path /etc/opencode)"
fi
if [[ -z "$ROOT" ]]; then
  systemctl daemon-reload
  systemctl reset-failed opencode.service opencode-web.service opencode-auth.service 2>/dev/null || true
  if ((purge)); then
    for user in opencode opencode-web opencode-auth; do if id "$user" >/dev/null 2>&1; then userdel "$user"; fi; done
  fi
  if ((restore_demo)); then systemctl start opencode-ui-demo.service; fi
fi
printf 'Removed isolated deployment. %s Octo, main nginx, reused firewall rules and external workspaces untouched.\n' "$([[ "$purge" == 1 ]] && printf 'OpenCode data/credentials purged.' || printf 'OpenCode data/credentials retained for reinstall.')"
