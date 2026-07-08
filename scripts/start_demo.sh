#!/bin/bash
# ============================================================
# start_demo.sh
# Demo entrypoint with mock-first navigation mode
# 负责人：熊浩宇
# ============================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
MODE=${1:-nav-mock}

cd "$PROJECT_ROOT"

echo "============================================="
echo " iCar ROS2 Patrol Demo Startup"
echo " mode: $MODE"
echo "============================================="

case "$MODE" in
    nav-mock)
        echo "[phase] navigation running in mock data mode"
        echo "[note] starts /map, /pose, /nav_status, /obstacle_status and /scan"
        ./scripts/start_navigation.sh mock-full
        ;;
    nav-mock-basic)
        echo "[phase] navigation basic mock data mode"
        ./scripts/start_navigation.sh mock
        ;;
    nav-mock-with-app)
        echo "[phase] navigation mock data mode + placeholders for app/task_manager"
        echo "[todo] start app_control_node and task_manager_node in their own terminals if they exist locally."
        ./scripts/start_navigation.sh mock-full
        ;;
    real)
        echo "[todo] real demo startup should be wired after the replacement vehicle arrives."
        exit 1
        ;;
    -h|--help|help)
        cat <<'EOF'
Usage:
  ./scripts/start_demo.sh [mode]

Modes:
  nav-mock          Start full navigation chain in mock data mode
  nav-mock-basic    Start /map, /pose and /nav_status only
  nav-mock-with-app Start navigation mock mode and leave notes for app/task_manager
  real              Placeholder for future real robot demo
EOF
        ;;
    *)
        echo "[error] unknown mode: $MODE"
        exit 1
        ;;
esac
