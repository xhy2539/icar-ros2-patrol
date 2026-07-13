#!/usr/bin/env bash
# Swap current and previous release links, then verify service health.

set -euo pipefail

DEPLOY_ROOT=${ICAR_DEPLOY_ROOT:-/home/jetson/icar-deploy}
CURRENT_LINK="$DEPLOY_ROOT/current"
PREVIOUS_LINK="$DEPLOY_ROOT/previous"
CURRENT_TARGET=$(readlink "$CURRENT_LINK" 2>/dev/null || true)
PREVIOUS_TARGET=$(readlink "$PREVIOUS_LINK" 2>/dev/null || true)

[[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" ]] || {
  echo "没有可回滚的上一版本" >&2
  exit 1
}

ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK"
if [[ -n "$CURRENT_TARGET" ]]; then
  ln -sfn "$CURRENT_TARGET" "$PREVIOUS_LINK"
fi

RESTART_COMMAND=${ICAR_RESTART_COMMAND:-systemctl restart icar_startup.service && systemctl restart icar_web_gateway.service}
HEALTH_COMMAND=${ICAR_HEALTH_COMMAND:-systemctl is-active --quiet icar_startup.service icar_web_gateway.service && curl --fail --silent --show-error --max-time 5 http://127.0.0.1:6500/health}
if bash -lc "$RESTART_COMMAND" && bash -lc "$HEALTH_COMMAND"; then
  echo "回滚成功: $PREVIOUS_TARGET"
  exit 0
fi

echo "回滚版本健康检查失败，恢复原 current" >&2
if [[ -n "$CURRENT_TARGET" ]]; then
  ln -sfn "$CURRENT_TARGET" "$CURRENT_LINK"
  ln -sfn "$PREVIOUS_TARGET" "$PREVIOUS_LINK"
  bash -lc "$RESTART_COMMAND" || true
fi
exit 1
