#!/usr/bin/env bash
# Stage and activate a verified release. Designed to run on the Jetson later,
# but --stage-only is fully testable on a development machine.

set -euo pipefail

usage() {
  echo "用法: $0 <archive.tar.gz> <archive.sha256> [--stage-only]" >&2
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 2
fi
ARCHIVE=$1
CHECKSUM=$2
MODE=${3:-}
[[ -z "$MODE" || "$MODE" == "--stage-only" ]] || { usage; exit 2; }

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEPLOY_ROOT=${ICAR_DEPLOY_ROOT:-/home/jetson/icar-deploy}
RELEASES_DIR="$DEPLOY_ROOT/releases"
mkdir -p "$RELEASES_DIR"

STAGING=$(mktemp -d "$DEPLOY_ROOT/.staging.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT
"$SCRIPT_DIR/verify_release_bundle.sh" "$ARCHIVE" "$CHECKSUM" "$STAGING"

SOURCE="$STAGING/icar-ros2-patrol"
VERSION=$(python3 - "$SOURCE/release-manifest.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["version"])
PY
)
[[ "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "发布版本号非法" >&2; exit 1; }
DESTINATION="$RELEASES_DIR/$VERSION"
ARCHIVE_HASH=$(awk 'NF {print tolower($1); exit}' "$CHECKSUM")

if [[ -e "$DESTINATION" ]]; then
  INSTALLED_HASH=$(cat "$DESTINATION/.icar_archive_sha256" 2>/dev/null || true)
  if [[ "$INSTALLED_HASH" != "$ARCHIVE_HASH" ]]; then
    echo "版本号 $VERSION 已存在但发布包哈希不同，拒绝覆盖不可变版本" >&2
    exit 1
  fi
  echo "版本已经暂存，保留现有目录: $DESTINATION"
else
  mv "$SOURCE" "$DESTINATION"
  printf '%s\n' "$ARCHIVE_HASH" > "$DESTINATION/.icar_archive_sha256"
  chmod +x "$DESTINATION/scripts/"*.sh
  echo "版本已暂存: $DESTINATION"
fi

if [[ "$MODE" == "--stage-only" ]]; then
  echo "离线暂存演练完成，未切换 current，也未启动任何服务"
  exit 0
fi

CURRENT_LINK="$DEPLOY_ROOT/current"
PREVIOUS_LINK="$DEPLOY_ROOT/previous"
OLD_TARGET=$(readlink "$CURRENT_LINK" 2>/dev/null || true)
OLD_PREVIOUS_TARGET=$(readlink "$PREVIOUS_LINK" 2>/dev/null || true)
if [[ ${ICAR_INSTALL_SYSTEMD:-1} == 1 && $(id -u) -ne 0 ]]; then
  echo "安装 systemd 服务需要 root；请以 root 运行或设置 ICAR_INSTALL_SYSTEMD=0" >&2
  exit 1
fi
if [[ -n "$OLD_TARGET" && "$OLD_TARGET" != "$DESTINATION" ]]; then
  ln -sfn "$OLD_TARGET" "$PREVIOUS_LINK"
fi
ln -sfn "$DESTINATION" "$CURRENT_LINK"

if [[ ${ICAR_INSTALL_SYSTEMD:-1} == 1 ]]; then
  install -m 0644 "$DESTINATION/scripts/icar_startup.service" /etc/systemd/system/icar_startup.service
  install -m 0644 "$DESTINATION/scripts/icar_web_gateway.service" /etc/systemd/system/icar_web_gateway.service
  systemctl daemon-reload
  systemctl enable icar_startup.service icar_web_gateway.service
fi

RESTART_COMMAND=${ICAR_RESTART_COMMAND:-systemctl restart icar_startup.service && systemctl restart icar_web_gateway.service}
HEALTH_COMMAND=${ICAR_HEALTH_COMMAND:-systemctl is-active --quiet icar_startup.service icar_web_gateway.service && curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health}

if bash -lc "$RESTART_COMMAND" && bash -lc "$HEALTH_COMMAND"; then
  echo "版本已激活并通过健康检查: $VERSION"
  exit 0
fi

echo "新版本健康检查失败，开始自动回滚" >&2
if [[ -n "$OLD_TARGET" ]]; then
  ln -sfn "$OLD_TARGET" "$CURRENT_LINK"
  if [[ -n "$OLD_PREVIOUS_TARGET" ]]; then
    ln -sfn "$OLD_PREVIOUS_TARGET" "$PREVIOUS_LINK"
  else
    rm -f "$PREVIOUS_LINK"
  fi
  bash -lc "$RESTART_COMMAND" || true
  echo "已恢复上一版本: $OLD_TARGET" >&2
else
  rm -f "$CURRENT_LINK"
  echo "没有上一版本可恢复，已移除 current 链接" >&2
fi
exit 1
