# 云平台与 CI/CD 实施计划

> 目标：手机和小车不在同一热点时，仍可安全控制小车、查看状态、下发巡检任务，并形成可测试、可回滚的自动交付流程。

2026-07-14 实车集中联调按 [《2026-07-14 实车一次性打通计划》](2026-07-14实车一次性打通计划.md) 执行；该 Runbook 是现场步骤、验收门和回滚依据。

## 一、当前已经完成（可离线验证）

- Flutter 支持“局域网直连 / 云端远程”双模式
- APP 可通过 MQTT 订阅小车在线状态、任务状态、导航、避障、环境数据、告警和日志
- APP 可通过 MQTT 下发巡检、LLM、报告和远程方向控制指令
- 远程方向控制采用 100ms 心跳、1 秒短租约；松手、APP 退后台、MQTT 断线或租约过期都会停车
- 云端速度进入 `/cmd_vel_cloud`，再由 `velocity_mux` 汇总到 `/cmd_vel`
- 控制优先级：安全急停 > 局域网 APP > 云端 APP > 跟踪 > 手柄 > 导航
- 云桥支持 MQTT 自动重连、Last Will、在线状态、命令 ACK、重复/过期任务过滤
- 高频导航和避障数据默认限频到 2Hz，告警不延迟
- 云端模式支持按需请求原始/标注 JPEG 截图；请求有过期、去重、限频、并发和 512 KiB 上限
- GitHub Actions 已包含 Python/Flutter 检查、72 项硬件无关 Python 测试、Release APK 构建、ROS2 发布包校验和构建产物保存
- 已提供版本化发布、SHA-256 校验、HTTPS 拉取、独立目录暂存、健康检查、自动回滚和手动回滚脚本

当前限制：小车离线，因此 ROS2 `colcon build`、车端运行和跨网络端到端测试尚未完成。

### 2026-07-13 离线收口结果

- 云服务器 HTTP 健康检查通过
- 使用隔离的 `/icar/offline-validation/<随机ID>` Topic 完成 MQTT QoS 1 发布/订阅回环测试；测试消息已清理，未触碰控制 Topic
- 云桥协议测试 18 项通过；全仓硬件无关 Python 测试 72 项通过
- Flutter 静态分析无问题，Flutter 测试 7 项通过
- 使用临时 JDK 17 重新构建 Release APK 成功，未修改系统 Java
- 发布包已完成生成、SHA-256 校验、隔离暂存、版本切换、手动回滚和健康检查失败自动回滚演练
- `icar_startup.sh` 已包含 `cloud_bridge` 的同步、编译、启动和 ROS 节点检查

因此，当前代码与发布链路中只剩必须依赖小车的 ROS2 Foxy 编译、容器/硬件运行和跨网络真机验收。

## 二、阶段计划

### 阶段 A：不依赖小车的云端验证

1. 在电脑上以测试客户端连接 MQTT Broker。
2. 订阅 `/icar/#`，确认 APP 上线后没有发布未授权运动指令。
3. 模拟发布 `/icar/online`、`/icar/status`、`/icar/nav`、`/icar/obstacle`、`/icar/env`、`/icar/alert` 和 `/icar/log`。
4. 验证 APP 页面实时刷新、日志解析和小车在线/离线切换。
5. 仅检查 `/icar/control` 消息格式，不连接真实底盘。
6. 向 `/icar/snapshot/request` 发布短期请求，模拟 `/icar/snapshot` 成功、失败及超大图片响应。

完成标准：APP 在任意网络可连接 Broker，模拟状态能够完整显示，离线状态下方向键和任务下发被阻止。

### 阶段 B：小车恢复后的车端部署

1. 备份小车当前 ROS2 工作空间和启动脚本。
2. 同步 `icar_interfaces`、`cloud_bridge`、`app_control`、`vision_patrol` 和相关脚本。
3. 安装 `paho-mqtt`，执行 `colcon build --packages-select icar_interfaces cloud_bridge app_control vision_patrol`。
4. 确认 `velocity_mux_node` 订阅 `/cmd_vel_cloud`，唯一输出到 `/cmd_vel`。
5. 启动 `cloud_bridge_node`，确认 `/icar/online` retained 状态为 `true`。
6. 先架空车轮或关闭驱动电源，只观察 `/cmd_vel_cloud` 和 `/cmd_vel`。
7. 依次验证 forward、backward、left、right、turn_left、turn_right 和 stop。
8. 验证停止条件：松手、杀掉 APP、关闭手机网络、停止 cloud_bridge、Broker 断线。
9. 验证安全停止始终覆盖本地和云端方向指令。
10. 确认 `vision_mjpeg_server` 仅监听 `127.0.0.1:6502`，依次请求原始/标注远程截图。

完成标准：任何心跳中断后 1.5 秒内 `/cmd_vel` 回到全零，且不会自动恢复运动。

### 阶段 C：跨网络完整联调

1. 手机使用 4G/5G，小车使用另一 Wi-Fi 或 4G 网络。
2. APP 云端连接后确认小车在线。
3. 测试任务下发及 `/icar/ack`。
4. 查看任务状态、导航、避障、传感器、告警和日志。
5. 在低速档测试远程方向键，记录指令延迟、停止延迟和丢包表现。
6. 执行 A/B/C 巡检闭环并生成报告。
7. 在 4G/5G 下连续请求 20 次远程截图，确认限频提示明确、APP 不崩溃且 MQTT 控制不受影响。

完成标准：不共享热点也能完成控制、状态查看和巡检闭环；断网、超时和异常情况下均能停车。

### 阶段 D：凭据与通信安全整改

1. 轮换当前测试 MQTT 和 SSH 凭据。
2. MQTT 改为 TLS 8883，APP 开启证书校验。
3. 设置设备级 Topic：`/icar/<device_id>/...`。
4. Mosquitto 配置 ACL，APP 不能访问其他设备 Topic。
5. APP 凭据从普通配置迁移到安全存储，后续改为短期令牌或云网关鉴权。
6. 清理 Git 当前版本及历史中的旧凭据。

### 阶段 E：CD 与回滚

小车通常位于 NAT/4G 网络后，GitHub Runner 无法稳定主动 SSH 进入小车，因此采用“构建端发布、小车端拉取”的方式：

1. GitHub Actions 在 `main` 或版本 Tag 上运行全部检查。
2. 生成 APK 和 ROS2 源码发布包，计算 SHA-256 并保存为 Artifact/Release。
3. 小车更新代理仅在收到批准的版本号后主动下载发布包。
4. 新版本解压到独立目录，执行 `colcon build`，不覆盖当前运行版本。
5. 通过节点、Topic、MQTT 在线状态和急停测试后切换版本。
6. 健康检查失败时自动切回上一版本。
7. 生产部署必须使用 GitHub Environment 人工审批。

阶段 E 的构建端和脚本端已经完成；首次安装服务、ROS2 编译和健康检查仍需在小车恢复后执行。

| 文件 | 作用 |
|------|------|
| `scripts/build_release_bundle.sh` | 生成带清单的版本化 ROS2/源码发布包和 SHA-256 |
| `scripts/verify_release_bundle.sh` | 校验哈希、阻止路径穿越并检查必要内容 |
| `scripts/pull_release.sh` | 只拉取显式批准的 HTTPS 发布地址 |
| `scripts/install_release.sh` | 独立目录暂存、切换 current、启动与失败自动回滚 |
| `scripts/rollback_release.sh` | 将 current/previous 切换并重新健康检查 |
| `.github/workflows/release.yml` | Tag/人工审批发布 APK 与 ROS2 包 |

离线生成和验证：

```bash
scripts/build_release_bundle.sh v1.0.0-rc1
scripts/verify_release_bundle.sh \
  dist/icar-ros2-v1.0.0-rc1.tar.gz \
  dist/icar-ros2-v1.0.0-rc1.tar.gz.sha256

ICAR_DEPLOY_ROOT=/tmp/icar-deploy-test \
  scripts/install_release.sh \
  dist/icar-ros2-v1.0.0-rc1.tar.gz \
  dist/icar-ros2-v1.0.0-rc1.tar.gz.sha256 \
  --stage-only
```

小车恢复后，从明确批准的 Release 拉取；不使用自动追踪 `latest`：

```bash
sudo ICAR_RELEASE_TOKEN="$GITHUB_TOKEN" scripts/pull_release.sh \
  "https://github.com/<owner>/<repo>/releases/download/v1.0.0/icar-ros2-v1.0.0.tar.gz" \
  "https://github.com/<owner>/<repo>/releases/download/v1.0.0/icar-ros2-v1.0.0.tar.gz.sha256"

sudo scripts/rollback_release.sh
```

## 三、端到端验收指标

| 项目 | 验收标准 |
|------|----------|
| 跨网络连接 | 手机、小车不同网络仍可连接 |
| 在线状态 | 云桥启动或断开后 5 秒内更新 |
| 状态刷新 | 导航、避障等常规状态约 2Hz |
| 巡检指令 | APP 收到明确 ACK，重复/过期任务被拒绝 |
| 方向控制 | 长按持续运动，松手立即发 stop |
| 断线停车 | 心跳中断后不超过 1.5 秒停车 |
| 安全优先级 | 急停状态下任何远程指令都不能驱动车辆 |
| 远程截图 | 10 秒内返回；单图不超过 512 KiB；失败返回明确错误 |
| 发布质量 | CI、Flutter 测试、ROS2 构建全部通过 |
| 回滚 | 新版本健康检查失败后恢复上一版本 |

## 四、建议执行顺序

`模拟云端状态 → 车轮架空测试 → 低速真车测试 → 跨网络巡检 → TLS/换密钥 → 自动部署与回滚`

## 五、远程视频演进

1. 当前阶段使用按需 MQTT 截图，适合弱网和告警取证，不持续占用带宽。
2. 连续远程视频采用 WebRTC：`/camera/color/image_raw` 或 `/vision/annotated_image` → Jetson H.264 硬件编码 → WebRTC。
3. 信令必须走已鉴权的 HTTPS/WSS，会话令牌不能使用长期 MQTT 密码。
4. 部署 STUN/TURN，并分别验收 P2P 与 TURN 中继；初始目标 480p、10–15 FPS、300–800 Kbps。
5. WebRTC 与 MQTT 控制完全分离，视频断开、降码率或 TURN 故障不得影响停车和控制心跳。
