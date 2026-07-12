# APP 接入指南


## 小车 APP 服务概况

| 项目 | 值 |
|------|-----|
| 服务地址 | `http://<小车IP>:6500` |
| WebSocket | `ws://<小车IP>:6500/ws/control` |
| 视频流 | `http://<小车IP>:6500/video_feed` |
| YOLO 视频流 | `http://<小车IP>:6500/yolo_video_feed` |
| Web 服务器 | gevent WSGIServer |
| 小车 IP | **不固定，见 `docs/小车配置`** |

## 一、视频流

### 原理

```
USB摄像头
    │ OpenCV VideoCapture 直读
    ▼
后台线程 _update_camera_frame()
    │ 死循环抓帧
    ▼
latest_frame (共享变量 + threading.Lock)
    │
    ▼
Flask Generator mode_handle()
    │ cv.imencode('.jpg')
    │ yield MJPEG 分片
    ▼
HTTP Response
  Content-Type: multipart/x-mixed-replace; boundary=frame
```

### 手机端显示

MJPEG 就是一个不断吐 JPEG 帧的 HTTP 流，所有框架都能直接用：

- **WebView**：直接 `<img src="http://<IP>:6500/video_feed">`
- **React Native**：`<Image source={{uri: "http://<IP>:6500/video_feed"}} />`
- **Flutter**：`Image.network("http://<IP>:6500/video_feed")`
- **原生 iOS**：URLSession 流式读取 + UIImageView
- **原生 Android**：HttpURLConnection 流式读取 + BitmapFactory + ImageView

> **注意**：MJPEG 是持续连接，不要把整个响应体读完了才显示。要边读边解码边刷新 ImageView。

### 关键代码（rosmaster_main.py）

```python
def mode_handle(self):
    while True:
        with self.frame_lock:
            frame = self.latest_frame.copy()
        ret, jpg = cv.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n')
```

---

## 二、底盘控制

### 原理

```
手机按钮
    │
    ▼ WebSocket 文本消息 "forward"
/ws/control (app.py Flask-Sock)
    │ socket.sendall("forward")
    ▼ TCP 127.0.0.1:6000
rosmaster_main.py 内部 TCP 服务
    │ 解析指令
    ▼ g_bot.set_car_run(state, speed)
Rosmaster_Lib 串口库
    │ 十六进制协议帧
    ▼ /dev/myserial (115200bps)
AT32 底盘控制板
    ▼
电机转动
```

### WebSocket 指令集

手机端连 `ws://<IP>:6500/ws/control`，发送纯文本指令：

| 指令 | 动作 |
|------|------|
| `forward` | 前进 |
| `backward` | 后退 |
| `left` | 左转 |
| `right` | 右转 |
| `stop` | 停止 |
| `start` | 启动 |

（实际指令字符串以 `rosmaster_main.py` 中 TCP 协议为准，建议连上车后 WebSocket 抓包确认完整指令表。）

### 底层调用

```python
# rosmaster_main.py 中的控制链
self.g_bot.set_car_run(state, speed)           # 命令模式（1前进/2后退/3左/4右/7停）
self.g_bot.set_car_motion(speed_x, speed_y, 0) # 速度模式
```

---

## 三、APP 端最小实现

```javascript
// 伪代码：React Native 示例
const WS_URL = "ws://10.90.164.83:6500/ws/control";
const VIDEO_URL = "http://10.90.164.83:6500/video_feed";

// 1. 连接控制通道
const ws = new WebSocket(WS_URL);
ws.send("forward");   // 前进
ws.send("stop");      // 停止

// 2. 显示视频
<Image source={{ uri: VIDEO_URL }} />

// 3. 后续拿 ROS2 数据（巡检状态等）
// 预留 WebSocket 订阅 /task/status
```

## 统一语音入口与意图路由

正式 APP 只显示一个“开始对话”入口，不让老人选择半双工、全双工或控制模式。
APP 将平台 ASR 或语音网关得到的用户文本发布到 `/voice/user_text`：

```json
{
  "text": "请开始巡检二楼走廊",
  "session_id": "voice_20260711_001",
  "timestamp": 1783753200
}
```

`voice_command_router_node` 自动发布 `/voice/intent`：

```json
{
  "intent": "robot_task",
  "confidence": 0.9,
  "requires_confirmation": true,
  "interaction": "confirm",
  "text": "请开始巡检二楼走廊",
  "source": "voice"
}
```

意图处理规则：

| intent | APP 行为 | 是否等待 LLM |
|---|---|---|
| `chat` | 保持语音对话 | 是 |
| `robot_task` | 显示/播报任务确认，确认后下发任务 | 是 |
| `care_alert` | 通知工作人员并向老人反馈 | 否 |
| `emergency` | 立即打断播放、触发急停和告警 | 否 |

APP 不发送 `/cmd_vel`。运动任务始终经过任务确认、`task_manager` 和安全白名单。

## 四、注意事项

1. **必须在同一局域网**，小车和手机连同一个 WiFi/热点。
2. **app.py 占串口**，启动它之前不要同时跑 ROS2 底盘驱动（`r`）。
3. **视频流不经过 ROS2**，是直读 USB 摄像头 + MJPEG HTTP。
4. 李雨晨的 APP 目前只需要**视频 + 控制**，巡检数据（/task/status 等）后续对接 ROS2 Topic。
