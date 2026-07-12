#!/usr/bin/env python3
"""Mac → MiniCPM-o → 小车音箱 (全双工). 空格键=静音/取消静音"""
import asyncio, websockets, json, base64, threading, socket, sys, time, subprocess, re, shlex
import numpy as np, sounddevice as sd
from pynput import keyboard as kb

mic_muted = False

def send_task_to_car(command_text):
    """解析语音命令并发送到小车 task_manager"""
    # 提取巡检点
    points = re.findall(r'[A-F]点|[A-F](?![a-zA-Z])|一二三四五六', command_text)
    route = []
    cn_map = {'一':'A','二':'B','三':'C','四':'D','五':'E','六':'F'}
    for p in points:
        p = p.replace('点','')
        route.append(cn_map.get(p, p))
    route = list(dict.fromkeys(route))  # 去重保序
    if not route:
        route = ['A']  # 默认A点

    task_type = 'patrol'
    params = json.dumps({'source': 'voice', 'command': command_text}, ensure_ascii=False)

    route_yaml = "[" + ",".join(route) + "]"
    msg_yaml = (
        f"{{task_type: {task_type}, route: {route_yaml}, "
        f"params: {json.dumps(params, ensure_ascii=False)}}}"
    )
    ros_cmd = (
        "source /opt/ros/foxy/setup.bash && "
        "source /root/icar_ros2_ws/icar_ws/install/setup.bash && "
        "ros2 topic pub --once /task/request icar_interfaces/msg/TaskRequest "
        f"{shlex.quote(msg_yaml)}"
    )
    docker_cmd = f"docker exec icar_ros2 bash -c {shlex.quote(ros_cmd)}"
    cmd = (
        f'sshpass -p "yahboom" ssh -o StrictHostKeyChecking=no '
        f"jetson@{CAR_IP} {shlex.quote(docker_cmd)}"
    )
    try:
        subprocess.run(cmd, shell=True, timeout=10, capture_output=True)
        print(f"\n✅ 已发送任务到小车: 路线={route}")
    except Exception as e:
        print(f"\n❌ 发送失败: {e}")

CAR_IP = "192.168.137.218"
CAR_PORT = 9999
MIC = "MacBook Air麦克风"

car_sock = None
car_lock = threading.Lock()
car_buffer = []
car_listen_since = None  # 开始聆听的时间

def car_send(audio_f32):
    global car_sock
    try:
        samples = np.frombuffer(audio_f32, dtype=np.float32)
        n = int(len(samples) * 16000 / 24000)
        samples = np.interp(np.linspace(0, len(samples)-1, n), np.arange(len(samples)), samples)
        data = (samples * 32767).astype(np.int16).tobytes()
        with car_lock:
            if car_sock is None:
                car_sock = socket.socket(); car_sock.settimeout(5)
                car_sock.connect((CAR_IP, CAR_PORT))
            car_sock.sendall(data)
        print(f"[+{len(data)}]", end="", flush=True)
    except:
        with car_lock: car_sock = None

def car_flush():
    pass  # 持久连接不需要 flush

async def main():
    print("连接...")
    ws = await websockets.connect(
        "ws://127.0.0.1:8040/ws/duplex/mac_voice", open_timeout=10)

    e = json.loads(await ws.recv())
    while e.get("type") != "queue_done":
        e = json.loads(await ws.recv())
    print("已连接!")

    await ws.send(json.dumps({
        "type": "prepare",
        "system_prompt": "你是巡检助手，用简短中文回复。确认任务后用'执行任务：'开头复述。",
        "config": {"generate_audio": True, "chunk_ms": 1000, "sample_rate": 16000, "temperature": 0.7}
    }))
    e = json.loads(await ws.recv())
    while e.get("type") != "prepared":
        e = json.loads(await ws.recv())
    print("就绪! 说话吧...  [空格]=静音/取消\n🎤\n")

    # 键盘监听: 空格切换静音
    def on_press(key):
        global mic_muted
        if key == kb.Key.space:
            mic_muted = not mic_muted
            print(f"\n{'🔇 麦克风已静音' if mic_muted else '🎤 麦克风已开启'}\n", end="", flush=True)
    kb.Listener(on_press=on_press, daemon=True).start()

    # 用 asyncio.Queue 桥接音频线程 → 异步发送
    aq = asyncio.Queue(maxsize=20)
    loop = asyncio.get_event_loop()
    running = True

    def mic_cb(indata, frames, t, status):
        if status or not running: return
        asyncio.run_coroutine_threadsafe(aq.put(bytes(indata)), loop)

    stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                             blocksize=1600, device=MIC, callback=mic_cb)
    stream.start()

    async def sender():
        global mic_muted
        count = 0
        buf = bytearray()
        CHUNK_SIZE = 16000 * 4  # 1 second @ 16kHz float32 = 64000 bytes
        while running:
            chunk = await asyncio.wait_for(aq.get(), timeout=0.5)
            if mic_muted:
                continue
            buf.extend(chunk)
            if len(buf) >= CHUNK_SIZE:
                data = bytes(buf[:CHUNK_SIZE])
                buf = buf[CHUNK_SIZE:]
                count += 1
                if count % 10 == 0:
                    print(f"[发送{count}]", end="", flush=True)
                await ws.send(json.dumps({"type": "audio_chunk",
                    "audio_base64": base64.b64encode(data).decode()}))
        while not aq.empty():
            aq.get_nowait()

    s_task = asyncio.create_task(sender())
    turn_text = ""
    was_speaking = False

    try:
        async for raw in ws:
            e = json.loads(raw)
            t = e.get("type")

            if t == "audio_only":
                ad = e.get("audio_data")
                if ad and len(str(ad)) > 100:
                    print("[A]", end="", flush=True)
                    threading.Thread(target=car_send, args=(base64.b64decode(ad),), daemon=True).start()
                continue

            if t != "result": continue

            is_speaking = not bool(e.get("is_listen", True))
            txt = str(e.get("text", ""))
            if txt:
                turn_text += txt
                sys.stdout.write(txt); sys.stdout.flush()

            ad = e.get("audio_data")
            if ad and len(str(ad)) > 100:
                print("[A]", end="", flush=True)
                threading.Thread(target=car_send, args=(base64.b64decode(ad),), daemon=True).start()

            turn_end = bool(e.get("end_of_turn")) or (was_speaking and not is_speaking)
            was_speaking = is_speaking
            if turn_end and turn_text.strip():
                print()
                if "执行任务：" in turn_text:
                    cmd = turn_text.split("执行任务：")[1].strip().split("。")[0]
                    print(f"\n🚗 任务: {cmd}")
                    threading.Thread(target=send_task_to_car, args=(cmd,), daemon=True).start()
                turn_text = ""

    except KeyboardInterrupt: pass
    finally:
        running = False
        s_task.cancel()
        stream.stop(); stream.close()
        car_flush()
        if car_sock: car_sock.close()
        await ws.close()
        print("\n结束")

asyncio.run(main())
