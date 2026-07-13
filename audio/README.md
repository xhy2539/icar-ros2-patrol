# 小车音频资源目录

此目录存放小车音箱播放的音频文件（.wav / .mp3 格式）。

## 预定义音频

| 文件名 | 名称 | 用途 |
|--------|------|------|
| `welcome.wav` | welcome | 欢迎语音 |
| `start_patrol.wav` | start_patrol | 开始巡检 |
| `complete.wav` | complete | 巡检完成 |
| `alert.wav` | alert | 告警提示 |
| `beep.wav` | beep | 短促提示音 |
| `stop.wav` | stop | 停止提示 |
| `danger.wav` | danger | 危险警告 |
| `info.wav` | info | 信息通知 |
| `error.wav` | error | 错误提示 |
| `bye.wav` | bye | 再见语音 |

## 生成音频文件

在 Jetson 上运行：

```bash
bash scripts/setup_audio.sh
```

也可用 TTS 工具生成中文语音（需要联网）：

```bash
pip3 install gtts
python3 -c "
from gtts import gTTS
samples = {
    'welcome': '你好，我是智能巡检小车，请下达指令',
    'start_patrol': '收到，开始执行巡检任务',
    'complete': '巡检任务已完成，一切正常',
    'bye': '任务结束，再见',
}
for name, text in samples.items():
    gTTS(text, lang='zh').save(f'audio/{name}.mp3')
    print(f'{name}.mp3 OK')
"
```

## LLM 工具调用

LLM 通过 `play_audio` 工具自动选择音频名称：
- "播放欢迎语音" → name="welcome"
- "嘀一声" → name="beep"
- "发警告" → name="alert"
