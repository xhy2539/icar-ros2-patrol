#!/bin/bash
# ============================================================
# start_navigation.sh
# Navigation startup entrypoint for real/mock modes
# 负责人：曹莹
# ============================================================

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
MODE=${1:-mock}
NAV_SCENARIO=${NAV_SCENARIO:-success}
OBSTACLE_SCENARIO=${OBSTACLE_SCENARIO:-warning_then_clear}
PATROL_ROUTE=${PATROL_ROUTE:-}
PIDS=()

cd "$PROJECT_ROOT"

print_usage() {
    cat <<'EOF'
Usage:
  ./scripts/start_navigation.sh [mode]

Modes:
  mock         Start /map, /pose and /nav_status in mock data mode
  mock-full    Start mock chain plus /obstacle_status, /scan and A/B/C patrol
  real         Placeholder for future real robot startup

Environment variables:
  NAV_SCENARIO        success | timeout | fail_fast
  OBSTACLE_SCENARIO   clear | warning_then_clear | danger_then_recover
  PATROL_ROUTE        Comma-separated route, e.g. A,B,C
EOF
}

start_process() {
    local name=$1
    shift
    echo "[start] $name -> $*"
    "$@" &
    PIDS+=($!)
}

cleanup() {
    if [ ${#PIDS[@]} -eq 0 ]; then
        return
    fi
    echo ""
    echo "[cleanup] stopping navigation mock processes..."
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "============================================="
echo " Navigation Module Startup"
echo " mode: $MODE"
echo " root: $PROJECT_ROOT"
echo "============================================="

case "$MODE" in
    mock)
        start_process "slam_node" python3 navigation/slam/slam_node.py
        start_process "navigation_node" python3 navigation/navigation/navigation_node.py --scenario "$NAV_SCENARIO"
        ;;
    mock-full)
        start_process "slam_node" python3 navigation/slam/slam_node.py
        start_process "navigation_node" python3 navigation/navigation/navigation_node.py --scenario "$NAV_SCENARIO"
        start_process "obstacle_avoid_node" python3 navigation/obstacle_avoid/obstacle_avoid_node.py --scenario "$OBSTACLE_SCENARIO"
        start_process "lidar_node" python3 navigation/lidar/lidar_node.py
        if [ -n "$PATROL_ROUTE" ]; then
            start_process "patrol_node" python3 navigation/navigation/patrol_node.py --route "$PATROL_ROUTE"
        else
            start_process "patrol_node" python3 navigation/navigation/patrol_node.py
        fi
        ;;
    real)
        echo "[todo] real robot startup is not wired into this repository yet."
        echo "[todo] use the Docker/container command chain after the vehicle is available."
        exit 1
        ;;
    -h|--help|help)
        print_usage
        exit 0
        ;;
    *)
        echo "[error] unknown mode: $MODE"
        print_usage
        exit 1
        ;;
esac

echo ""
echo "Navigation module is running."
echo "Press Ctrl+C to stop all started processes."
wait
