#!/usr/bin/env bash
# Pull one explicitly approved release and hand it to install_release.sh.

set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "用法: $0 <archive-url> <sha256-url> [--stage-only]" >&2
  exit 2
fi
ARCHIVE_URL=$1
CHECKSUM_URL=$2
MODE=${3:-}

if [[ ${ICAR_ALLOW_HTTP_RELEASES:-0} != 1 ]]; then
  [[ "$ARCHIVE_URL" == https://* && "$CHECKSUM_URL" == https://* ]] || {
    echo "发布下载必须使用 HTTPS；测试 HTTP 时需显式设置 ICAR_ALLOW_HTTP_RELEASES=1" >&2
    exit 1
  }
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/icar-pull.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT
ARCHIVE="$TMP_DIR/release.tar.gz"
CHECKSUM="$TMP_DIR/release.tar.gz.sha256"
CURL_ARGS=(--fail --location --silent --show-error --retry 3)
if [[ -n ${ICAR_RELEASE_TOKEN:-} ]]; then
  CURL_ARGS+=(--header "Authorization: Bearer $ICAR_RELEASE_TOKEN")
fi
curl "${CURL_ARGS[@]}" "$ARCHIVE_URL" -o "$ARCHIVE"
curl "${CURL_ARGS[@]}" "$CHECKSUM_URL" -o "$CHECKSUM"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -n "$MODE" ]]; then
  exec "$SCRIPT_DIR/install_release.sh" "$ARCHIVE" "$CHECKSUM" "$MODE"
fi
exec "$SCRIPT_DIR/install_release.sh" "$ARCHIVE" "$CHECKSUM"
