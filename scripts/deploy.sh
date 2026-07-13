#!/bin/bash
# ============================================================
# deploy.sh — 一键部署到小车（开发快速部署）
#
# 将本地改动 push 后，SSH 到小车 git pull + 编译 + 重启服务
#
# 用法:
#   ./scripts/deploy.sh              # 部署+编译+重启
#   ./scripts/deploy.sh --no-restart # 只部署不重启
#   ./scripts/deploy.sh --restart    # 只重启服务
#
# 车端目录: ~/icar-ros2-patrol/  (git clone)
# 容器: autodrive_ros2 + icar_ros2
# ============================================================

set -euo pipefail

CAR_IP="${ICAR_IP:-192.168.137.117}"
CAR_USER="${ICAR_USER:-jetson}"
CAR_PASS="${ICAR_PASS:-yahboom}"
REPO_DIR="icar-ros2-patrol"
ROS_DOMAIN=30

# ---- 容器 → ROS2 包映射 ----
declare -A CONTAINER_PACKAGES
CONTAINER_PACKAGES[autodrive_ros2]="app_control cloud_bridge task_manager navigation icar_interfaces"
CONTAINER_PACKAGES[icar_ros2]="llm vision voice"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()   { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

modes=""
for arg in "${@}"; do
  case "$arg" in
    --no-restart) modes+="no-restart," ;;
    --restart)    modes+="restart,"    ;;
    *)            err "未知参数: $arg (可用: --no-restart, --restart)" ;;
  esac
done

# ---- SSH 带密码 ----
ssh_car() {
  expect -c "
  set timeout 60
  spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 $CAR_USER@$CAR_IP \"$*\"
  expect { \"password:\" { send \"$CAR_PASS\r\"; exp_continue } timeout { exit 1 } eof }
  " 2>&1
}

ssh_car_raw() {
  SSHPASS="$CAR_PASS" sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "$CAR_USER@$CAR_IP" "$@"
}

# ═══════════════════════════════════════════
# 仅重启模式
# ═══════════════════════════════════════════
if [[ "$modes" == "restart," ]]; then
  log "仅重启服务..."
  ssh_car_raw "sudo systemctl restart icar_startup.service icar_web_gateway.service"
  sleep 3
  ssh_car_raw "curl -s --max-time 3 http://127.0.0.1:6500/health"
  echo ""
  log "重启完成"
  exit 0
fi

# ═══════════════════════════════════════════
# Step 1: 检测连接
# ═══════════════════════════════════════════
log "检测小车连接 $CAR_USER@$CAR_IP ..."
if ! ssh_car_raw "echo OK" 2>/dev/null; then
  warn "无法 SSH 连接，检查 IP 和网络"
  exit 1
fi
log "SSH 连接正常"

# ═══════════════════════════════════════════
# Step 2: Git pull 最新代码
# ═══════════════════════════════════════════
log "拉取最新代码..."
ssh_car_raw "cd ~/$REPO_DIR && git pull 2>&1" || warn "git pull 失败，继续使用已有代码"

# ═══════════════════════════════════════════
# Step 3: 同步代码到容器并编译
# ═══════════════════════════════════════════
for container in autodrive_ros2 icar_ros2; do
  packages="${CONTAINER_PACKAGES[$container]}"
  ws_dir="/root/${container}_ws"

  log ">>> 容器 $container: 同步 $packages"

  # 同步代码
  ssh_car_raw "cd ~/$REPO_DIR && tar cf - $packages 2>/dev/null | docker exec -i $container bash -c 'mkdir -p $ws_dir/src && cd $ws_dir/src && rm -rf $packages && tar xf - && echo SYNC_OK'"

  # 编译
  log ">>> 容器 $container: colcon build..."
  ssh_car_raw "docker exec $container bash -lc 'source /opt/ros/foxy/setup.bash && cd $ws_dir && colcon build --symlink-install 2>&1 | tail -8'"
done

# ═══════════════════════════════════════════
# Step 4: 更新宿主机文件
# ═══════════════════════════════════════════
log "更新宿主机 web_gateway 和脚本..."
ssh_car_raw "cp ~/$REPO_DIR/app/web_gateway.py ~/icar-deploy/current/app/ 2>/dev/null || true"
ssh_car_raw "cp ~/$REPO_DIR/scripts/icar_startup.sh ~/icar-deploy/current/scripts/ 2>/dev/null || true"

# ═══════════════════════════════════════════
# Step 5: 重启服务
# ═══════════════════════════════════════════
if [[ "$modes" != "no-restart," ]]; then
  log "重启所有服务..."
  ssh_car_raw "sudo systemctl restart icar_startup.service icar_web_gateway.service 2>/dev/null" || {
    warn "systemd 不可用，用 icar_startup.sh 启动"
    ssh_car_raw "cd ~/$REPO_DIR && bash scripts/icar_startup.sh 2>&1 | tail -10"
  }

  sleep 5
  log "健康检查..."
  ssh_car_raw "curl -s --max-time 3 http://127.0.0.1:6500/health 2>&1" || warn "健康检查失败，登录小车检查"
fi

echo ""
log "================ 部署完成 ================"
log "健康: http://$CAR_IP:6500/health"
log "视频: http://$CAR_IP:6500/video_feed"
log "控制: ws://$CAR_IP:6500/ws/control"
