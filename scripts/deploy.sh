#!/bin/bash
# ============================================================
# deploy.sh — 一键部署到小车并编译运行
#
# 用法（在你 Mac 上执行）：
#   ./scripts/deploy.sh              # 部署+编译，不启动
#   ./scripts/deploy.sh --run        # 部署+编译+启动 mock demo
#
# 前提：
#   - 小车 IP 可访问（默认 10.90.164.83）
#   - 本机代码已 git push
# ============================================================

set -e

CAR_IP="${ICAR_IP:-10.90.164.83}"
CAR_USER="${ICAR_USER:-jetson}"
CAR_PASS="${ICAR_PASS:-yahboom}"
CONTAINER="icar_ros2"
WS_DIR="/root/ros2_ws"
REPO_DIR="icar-ros2-patrol"
PACKAGES="icar_interfaces task_manager cloud_bridge vision scripts"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---- Step 1: 检测 SSH 连接 ----
log "检测小车连接 $CAR_USER@$CAR_IP ..."
if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes "$CAR_USER@$CAR_IP" "echo ok" 2>/dev/null; then
    log "需要密码登录，请确保 expect 可用"
fi

# ---- Step 2: 拉取最新代码 ----
log "拉取最新代码到小车..."
expect -c "
set timeout 30
spawn ssh -o StrictHostKeyChecking=no $CAR_USER@$CAR_IP \"cd ~/$REPO_DIR 2>/dev/null && git pull || (git clone https://github.com/xhy2539/icar-ros2-patrol.git ~/$REPO_DIR && echo CLONED)\"
expect { \"password:\" { send \"$CAR_PASS\r\"; exp_continue } timeout { exit 1 } eof }
" 2>&1 | tail -5 || log "代码拉取可能失败（检查 GitHub 连通性），使用本地已有代码继续"

# ---- Step 3: 拷贝到 Docker 容器 ----
log "同步代码到 Docker 容器 $CONTAINER ..."
expect -c "
set timeout 20
spawn ssh -o StrictHostKeyChecking=no $CAR_USER@$CAR_IP \"cd ~/$REPO_DIR && tar cf - $PACKAGES 2>/dev/null | docker exec -i $CONTAINER bash -c 'mkdir -p $WS_DIR/src && cd $WS_DIR/src && rm -rf $PACKAGES && tar xf - && echo SYNC_OK'\"
expect { \"password:\" { send \"$CAR_PASS\r\"; exp_continue } timeout { exit 1 } eof }
" 2>&1 | grep -E "SYNC_OK|Error" || err "代码同步失败"

# ---- Step 4: 编译 ----
log "编译 ROS2 包（需要约 1 分钟）..."
expect -c "
set timeout 180
spawn ssh -o StrictHostKeyChecking=no $CAR_USER@$CAR_IP \"docker exec $CONTAINER bash -c 'cd $WS_DIR && source /opt/ros/foxy/setup.bash && colcon build --symlink-install'\"
expect { \"password:\" { send \"$CAR_PASS\r\"; exp_continue } timeout { exit 1 } eof }
" 2>&1 | tail -5

echo ""
log "部署完成！"
log "代码位置: 车上 ~/$REPO_DIR/  → 容器内 $WS_DIR/src/"
log "编译产物: 容器内 $WS_DIR/install/"

# ---- Step 5: 可选启动 ----
if [ "${1:-}" = "--run" ]; then
    echo ""
    log "启动 mock demo（不会让小车移动）..."
    expect -c "
set timeout 30
spawn ssh -o StrictHostKeyChecking=no $CAR_USER@$CAR_IP \"docker exec $CONTAINER bash -c 'source $WS_DIR/install/setup.bash && ros2 run task_manager task_manager_node & sleep 1 && ros2 run task_manager mock_navigation_node & sleep 1 && ros2 run task_manager mock_sensor_node & sleep 1 && ros2 run task_manager mock_vision_node & sleep 1 && ros2 run task_manager report_generator_node & sleep 1 && ros2 run task_manager mock_app_node & sleep 15' \"
expect { \"password:\" { send \"$CAR_PASS\r\"; exp_continue } timeout { exit 1 } eof }
" 2>&1 | grep -E "\[INFO\]|巡检报告|DONE|状态转换"
fi
