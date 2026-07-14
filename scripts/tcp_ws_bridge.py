#!/usr/bin/env python3
"""Minimal TCP→WebSocket bridge for the iCar app_bridge.

Connects directly to the car's app_bridge TCP port (6501) and exposes a
clean WebSocket for the browser.  Bypasses web_gateway's flaky Flask-Sock.
"""

import asyncio
import json
import os
import signal
import socket
import sys

import websockets
from websockets.asyncio.server import serve

WS_HOST = "127.0.0.1"
WS_PORT = 8765
CAR_HOST = os.getenv("ICAR_CAR_HOST", "10.247.5.83")
CAR_PORT = 6501  # app_bridge TCP (not web_gateway)


async def relay(reader, writer):
    """Bidirectional relay between TCP reader and WebSocket writer."""
    loop = asyncio.get_running_loop()
    buffer = b""
    while True:
        try:
            chunk = await loop.run_in_executor(None, reader.read, 4096)
        except OSError:
            break
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                await writer.send(text)


async def handle(ws):
    peer = ws.remote_address
    print(f"Browser connected: {peer}")
    tcp = socket.create_connection((CAR_HOST, CAR_PORT), timeout=5)
    tcp.setblocking(False)
    loop = asyncio.get_running_loop()

    async def tcp_to_ws():
        buffer = b""
        while True:
            try:
                chunk = await loop.run_in_executor(None, tcp.recv, 4096)
            except (BlockingIOError, InterruptedError):
                await asyncio.sleep(0.01)
                continue
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    await ws.send(text)

    tcp_task = asyncio.create_task(tcp_to_ws())
    try:
        async for msg in ws:
            tcp.sendall(msg.strip().encode() + b"\n")
    finally:
        tcp_task.cancel()
        try:
            tcp.close()
        except OSError:
            pass
        print(f"Browser disconnected: {peer}")


async def main():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    async with serve(handle, WS_HOST, WS_PORT):
        print(f"TCP→WS bridge: ws://{WS_HOST}:{WS_PORT} → {CAR_HOST}:{CAR_PORT}")
        await stop.wait()


if __name__ == "__main__":
    asyncio.run(main())
