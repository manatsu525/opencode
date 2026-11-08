#!/usr/bin/env bash
# Shared constants: never source a file containing user secrets here.
set -euo pipefail
VERSION=1.19.5
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=${DESTDIR:-}
export VERSION HERE
[[ -z "$ROOT" || ( "$ROOT" == /* && "$ROOT" != / && "$ROOT" != *..* ) ]] || { printf "Invalid DESTDIR\n" >&2; exit 1; }
path() { printf '%s%s' "$ROOT" "$1"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
asset_name() {
  local arch=${1:-$(uname -m)} libc=${2:-auto} variant=${OPENCODE_X64_VARIANT:-baseline} suffix=
  case "$arch" in aarch64|arm64) arch=arm64 ;; x86_64|amd64|x64) arch=x64 ;; *) fail "Unsupported architecture: $arch" ;; esac
  if [[ "$libc" == auto ]]; then
    case "$(ldd --version 2>&1 || :)" in *musl*) libc=musl ;; *) libc=glibc ;; esac
  fi
  [[ "$libc" == glibc || "$libc" == musl ]] || fail 'libc must be glibc or musl'
  if [[ "$arch" == x64 ]]; then
    case "$variant" in baseline) suffix=-baseline ;; standard) ;; *) fail 'Invalid x64 variant' ;; esac
  fi
  [[ "$libc" != musl ]] || suffix+=-musl
  printf 'opencode-linux-%s%s.tar.gz\n' "$arch" "$suffix"
}
validate_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1024 && 10#$1 <= 65535 )); }
