#!/usr/bin/env python3
"""本地对话: Mac麦克风 → MiniCPM-o → macOS say播放"""
import asyncio, websockets, json, base64, sys, os, wave, subprocess, uuid, threading
import numpy as np, sounddevice as sd

GATEWAY = "ws://127.0.0.1:8040/ws/duplex/local_chat"
MIC = "MacBook Air麦克风"
SAY_VOICE = "Flo (中文（中国大陆）)"
tts_lock = threading.Lock()

def say_and_play(text):
    with tts_lock:
        uid = uuid.uuid4().hex[:8]
        aiff = f"/tmp/tts_{uid}.aiff"
        wav = f"/tmp/tts_{uid}.wav"
        subprocess.run(["say","-v",SAY_VOICE,"-o",aiff,text], capture_output=True, timeout=30)
        if os.path.exists(aiff):
            subprocess.run(["afconvert","-f","WAVE","-d","LEI16@44100","-c","1",aiff,wav], capture_output=True, timeout=10)
            try: os.unlink(aiff)
            except: pass
        if os.path.exists(wav):
            # 直接播放wav
            import wave as wv
            with wv.open(wav,'rb') as f:
                fs = f.getframerate()
                raw = f.readframes(f.getnframes())
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(audio, fs)
            sd.wait()
            try: os.unlink(wav)
            except: pass

async def main():
    print("连接...")
    ws = await websockets.connect(GATEWAY, open_timeout=10)
    e = json.loads(await ws.recv())
    while e.get("type") != "queue_done": e = json.loads(await ws.recv())
    print("已连接!\n")

    await ws.send(json.dumps({
        "type":"prepare",
        "system_prompt":"你是巡检助手，用简短中文交流。",
        "config":{"generate_audio":False,"chunk_ms":1000,"sample_rate":16000,"temperature":0.7}
    }))
    e = json.loads(await ws.recv())
    while e.get("type") != "prepared": e = json.loads(await ws.recv())
    print("🎤 就绪! 说话吧... (Ctrl+C退出)\n")

    aq = asyncio.Queue(maxsize=30)
    loop = asyncio.get_event_loop()
    running = True

    def mic_cb(indata, frames, t, status):
        if status or not running: return
        asyncio.run_coroutine_threadsafe(aq.put(bytes(indata)), loop)

    stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1600, device=MIC, callback=mic_cb)
    stream.start()

    async def sender():
        buf = bytearray()
        CHUNK = 16000 * 4
        while running:
            try:
                chunk = await asyncio.wait_for(aq.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            buf.extend(chunk)
            if len(buf) >= CHUNK:
                data = bytes(buf[:CHUNK]); buf = buf[CHUNK:]
                await ws.send(json.dumps({"type":"audio_chunk","audio_base64":base64.b64encode(data).decode()}))

    s_task = asyncio.create_task(sender())
    turn_text = ""
    tts_task = None

    try:
        async for raw in ws:
            e = json.loads(raw)
            if e.get("type") != "result": continue
            txt = str(e.get("text",""))
            if txt:
                turn_text += txt
                sys.stdout.write(txt); sys.stdout.flush()

            if bool(e.get("end_of_turn")) and turn_text.strip():
                print(" ✓")
                if tts_task: tts_task.cancel()
                final = turn_text.rstrip()
                turn_text = ""

                async def do_tts(text):
                    await asyncio.sleep(2.0)
                    threading.Thread(target=say_and_play, args=(text,), daemon=True).start()
                tts_task = asyncio.create_task(do_tts(final))

    except KeyboardInterrupt: pass
    finally:
        running = False; s_task.cancel()
        stream.stop(); stream.close()
        await ws.close()
        print("\n结束")

asyncio.run(main())
