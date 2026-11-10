#!/usr/bin/env bash
# Completely remove this OpenCode deployment. Standalone: no helper files needed, so it works as
#   sudo opencode-uninstall
#   curl -fsSL https://raw.githubusercontent.com/manatsu525/opencode/manatsu/v1.19.5/deploy/uninstall.sh | sudo bash
#   sudo bash /opt/opencode/deploy/uninstall.sh
# Default = full purge after ONE terminal confirmation (Enter = yes). --yes skips the prompt (required
# when no terminal is available). --keep-data keeps sessions/workspace/credentials/certificate/config.
# Never touches octo, the main nginx service, external workspaces, pre-existing firewall rules or apt packages.
set -euo pipefail
ROOT=${DESTDIR:-}
[[ -z "$ROOT" || ( "$ROOT" == /* && "$ROOT" != / && "$ROOT" != *..* ) ]] || { printf 'Invalid DESTDIR\n' >&2; exit 1; }
path() { printf '%s%s' "$ROOT" "$1"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
validate_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1024 && 10#$1 <= 65535 )); }
usage() { printf 'Usage: opencode-uninstall [--yes] [--keep-data] [--restore-demo]\n'; }
yes=0 keep=0 restore_demo=0
while (($#)); do
  case "$1" in
    -y|--yes) yes=1 ;;
    --keep-data) keep=1 ;;
    --purge) keep=0 ;;  # accepted for compatibility; full removal is the default
    --restore-demo) restore_demo=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "Unknown option: $1" ;;
  esac
  shift
done
[[ -n "$ROOT" ]] || (( EUID == 0 )) || fail 'Run with sudo/root, e.g. sudo opencode-uninstall'
if ((!yes)); then
  if ((keep)); then question='确定要卸载 OpenCode 吗？（保留会话、工作区、凭据和证书）[Y/n] '
  else question='确定要彻底卸载 OpenCode 吗？（删除全部会话、默认工作区、凭据、证书和配置，不可恢复）[Y/n] '
  fi
  # A pipe (curl | sudo bash) occupies stdin, so always ask on the controlling terminal.
  if ! { exec 3<>/dev/tty; } 2>/dev/null; then
    fail 'No terminal for confirmation; rerun with --yes to uninstall non-interactively'
  fi
  printf '%s' "$question" >&3
  answer=
  IFS= read -r answer <&3 || answer=n   # EOF/Ctrl-D cancels
  exec 3>&-
  case "$answer" in ''|[Yy]|[Yy][Ee][Ss]|是) ;; *) printf 'Cancelled; nothing removed.\n'; exit 1 ;; esac
fi
units=(opencode-image-cleanup.timer opencode-image-cleanup.service opencode-web.service opencode-auth.service opencode.service)
if [[ -z "$ROOT" ]]; then
  systemctl disable --now "${units[@]}" >/dev/null 2>&1 || true
  # Only the firewall rule this installer added and recorded is removed.
  if [[ -f /etc/opencode/firewall-owned-port ]]; then
    read -r port </etc/opencode/firewall-owned-port
    validate_port "$port" || fail 'Invalid owned firewall record'
    iptables -D INPUT -p tcp --dport "$port" -m comment --comment opencode-web -j ACCEPT 2>/dev/null || true
    if systemctl is-active --quiet netfilter-persistent.service; then netfilter-persistent save >/dev/null 2>&1 || true; fi
  fi
fi
for unit in "${units[@]}"; do rm -f -- "$(path "/etc/systemd/system/$unit")"; done
# Binaries, frontend, deploy helpers/backups, the isolated nginx runtime + access log.
rm -rf -- "$(path /opt/opencode)" "$(path /var/lib/opencode-web)"
if ((!keep)); then
  # Sessions, default workspace, caches, cookie-login state, downloaded images, credentials, TLS cert,
  # nginx config and the image_search/keenable_search MCP config + global rules.
  rm -rf -- "$(path /var/lib/opencode)" "$(path /var/cache/opencode)" "$(path /var/lib/opencode-auth)" "$(path /var/lib/opencode-images)" "$(path /etc/opencode)"
fi
if [[ -z "$ROOT" ]]; then
  systemctl daemon-reload
  systemctl reset-failed "${units[@]}" >/dev/null 2>&1 || true
  if ((!keep)); then
    for user in opencode opencode-web opencode-auth; do
      if id "$user" >/dev/null 2>&1; then userdel "$user" >/dev/null 2>&1 || true; fi
      if getent group "$user" >/dev/null 2>&1; then groupdel "$user" >/dev/null 2>&1 || true; fi
    done
  fi
  if ((restore_demo)); then systemctl start opencode-ui-demo.service; fi
fi
# Remove the short command last (bash keeps the open script, so self-removal is safe).
rm -f -- "$(path /usr/local/bin/opencode-uninstall)"
if ((keep)); then
  printf 'OpenCode uninstalled; data, credentials, certificate and config kept for reinstall (remove later: curl -fsSL https://raw.githubusercontent.com/manatsu525/opencode/manatsu/v1.19.5/deploy/uninstall.sh | sudo bash).\n'
else
  printf 'OpenCode completely removed (services, files, data, credentials, certificate, users, owned firewall rule, opencode-uninstall). Octo, main nginx, external workspaces and apt packages untouched.\n'
fi
