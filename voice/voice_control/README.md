# voice_control

ROS2 bridge for MiniCPM-o full-duplex voice interaction.

Install runtime dependencies in the ROS2 container:

```bash
pip install numpy sounddevice websockets
```

Run the Mac MiniCPM-o gateway first, then start on the audio device host:

```bash
ros2 run voice_control duplex_audio_node --ros-args \
  -p server_url:=wss://MAC_IP:8040 \
  -p verify_tls:=false

ros2 run voice_control voice_command_router_node
```

Topics:

- `/voice/assistant_result`: streamed model text/result JSON
- `/voice/user_text`: user ASR text from the APP or audio gateway
- `/voice/intent`: automatic intent decision (`chat`, `robot_task`, `care_alert`, `emergency`)
- `/voice/status`: duplex connection state
- `/voice/control`: emergency stop events consumed by `task_manager`
- `/voice/robot_status`: task state for the app/voice feedback path
- `/task/request`: confirmed high-level task requests

The model never publishes `/cmd_vel`. Movement still passes through
`llm_gateway`, `task_manager`, navigation, and the existing safety checks.

The APP exposes one voice entry point. It does not ask the user to choose a
technical mode. Intent routing is automatic: chat continues normally, robot
tasks require confirmation, care alerts notify staff, and emergencies interrupt
the conversation immediately.

## 网页麦克风联调

控制模拟器在 `http://127.0.0.1:8088/web/control_simulator.html` 提供“语音”按钮。
浏览器将 16 kHz 单声道 PCM 发送到本机 `ws://127.0.0.1:8765/ws/voice`，由
`scripts/local_control_ws_proxy.py` 转发到小车的 `web_voice_gateway_node`
（默认端口 `8767`）。豆包凭据仅通过小车环境变量 `DOUBAO_APP_ID` 与
`DOUBAO_ACCESS_KEY` 提供；回复音频仅从车载音箱播放。
