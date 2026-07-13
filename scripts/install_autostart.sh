#!/bin/bash
# ============================================================
# install_autostart.sh — 在 Jetson 上安装自启动服务
#
# 用法（在车上执行）：
#   cd ~/icar-ros2-patrol
#   sudo bash scripts/install_autostart.sh
#
# 安装后：
#   - 开机自动启动 iCar 全栈
#   - 崩溃自动重启
#   - systemctl status icar_startup 查看状态
# ============================================================

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root 权限，请用 sudo 运行" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 安装 iCar 自启动服务 ==="

# 1. 安装 systemd service 文件
install -m 0644 "$SCRIPT_DIR/icar_startup.service" /etc/systemd/system/icar_startup.service
install -m 0644 "$SCRIPT_DIR/icar_web_gateway.service" /etc/systemd/system/icar_web_gateway.service

# 2. 确保启动脚本可执行
chmod +x "$SCRIPT_DIR/icar_startup.sh"
chmod +x "$SCRIPT_DIR/start_car_app_stack.sh" 2>/dev/null || true

# 3. 重载 systemd
systemctl daemon-reload

# 4. 启用自启动
systemctl enable icar_startup.service icar_web_gateway.service

echo ""
echo "=== 安装完成 ==="
echo ""
echo "管理命令："
echo "  启动:    sudo systemctl start icar_startup icar_web_gateway"
echo "  停止:    sudo systemctl stop icar_startup icar_web_gateway"
echo "  状态:    sudo systemctl status icar_startup icar_web_gateway"
echo "  日志:    sudo journalctl -u icar_startup -f"
echo "  禁用:    sudo systemctl disable icar_startup icar_web_gateway"
echo "  禁用后恢复手动启动: sudo bash $SCRIPT_DIR/icar_startup.sh"
echo ""
echo "健康检查: curl http://127.0.0.1:6500/health"
echo ""

# 5. 询问是否立即启动
read -rp "是否立即启动服务？[y/N] " answer
if [ "${answer,,}" = "y" ]; then
  echo "正在启动..."
  systemctl start icar_startup.service
  sleep 5
  systemctl start icar_web_gateway.service
  sleep 3
  echo ""
  systemctl status --no-pager icar_startup.service icar_web_gateway.service 2>/dev/null || true
  echo ""
  curl -s --max-time 3 http://127.0.0.1:6500/health 2>/dev/null || echo "（稍等几秒后健康检查就绪）"
fi
