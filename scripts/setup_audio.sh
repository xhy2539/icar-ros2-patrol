#!/bin/bash
# 小车音频文件生成脚本
# 在 Jetson 上运行：bash scripts/setup_audio.sh
# 需要 ffmpeg（小车已有）

set -e

AUDIO_DIR="${ICAR_AUDIO_DIR:-/home/jetson/icar-ros2-patrol/audio}"
mkdir -p "$AUDIO_DIR"
cd "$AUDIO_DIR" || exit 1

echo "=== 生成音频文件到 $AUDIO_DIR ==="

# ── 短促提示音 (beep) ──
ffmpeg -y -f lavfi -i "sine=frequency=800:duration=0.12" \
       -af "volume=0.4,afade=t=in:d=0.01,afade=t=out:st=0.08:d=0.04" \
       -ar 24000 -ac 1 beep.wav 2>/dev/null
echo "✓ beep.wav"

# ── 告警音 (alert) ──
ffmpeg -y -f lavfi -i "sine=frequency=800:duration=0.5" \
       -af "volume=0.5" -ar 24000 -ac 1 alert.wav 2>/dev/null
echo "✓ alert.wav"

# ── 危险警告 (danger) ──
ffmpeg -y -f lavfi -i "sine=frequency=1200:duration=0.3" \
       -af "volume=0.6" -ar 24000 -ac 1 danger.wav 2>/dev/null
echo "✓ danger.wav"

# ── 完成音 (complete) ──
ffmpeg -y -f lavfi -i "sine=frequency=600:duration=0.6" \
       -af "volume=0.5" -ar 24000 -ac 1 complete.wav 2>/dev/null
echo "✓ complete.wav"

# ── 信息提示音 (info) ──
ffmpeg -y -f lavfi -i "sine=frequency=500:duration=0.25" \
       -af "volume=0.3" -ar 24000 -ac 1 info.wav 2>/dev/null
echo "✓ info.wav"

# ── 停止音 (stop) ──
ffmpeg -y -f lavfi -i "sine=frequency=300:duration=0.4" \
       -af "volume=0.5" -ar 24000 -ac 1 stop.wav 2>/dev/null
echo "✓ stop.wav"

# ── 错误音 (error) ──
ffmpeg -y -f lavfi -i "sine=frequency=200:duration=0.5" \
       -af "volume=0.5" -ar 24000 -ac 1 error.wav 2>/dev/null
echo "✓ error.wav"

# ── TTS 语音（需要 gTTS，可选） ──
if python3 -c "import gtts" 2>/dev/null; then
    python3 << 'PYEOF'
from gtts import gTTS
samples = {
    'welcome': '你好，我是智能巡检小车，请下达指令。',
    'start_patrol': '收到，开始执行巡检任务。',
    'bye': '任务结束，再见。',
}
for name, text in samples.items():
    tts = gTTS(text, lang='zh')
    tts.save(f'{name}.mp3')
    print(f'✓ {name}.mp3 (TTS)')
PYEOF
else
    for name in welcome start_patrol bye; do
        cp beep.wav "${name}.wav"
    done
    echo "⚠ gTTS 未安装，语音文件用 beep 替代"
    echo "  安装: pip3 install gtts"
fi

echo ""
echo "=== 完成 ==="
ls -la "$AUDIO_DIR"
