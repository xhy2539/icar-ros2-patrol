#!/usr/bin/env python3
"""Loopback-only proxies for the local control simulator.

Browsers may block a localhost page from opening a WebSocket directly to a
private-network device. These proxies keep browser traffic on loopback and
forward control frames plus the camera/status HTTP endpoints to the car.
"""

import asyncio
import http.server
import http.client
import json
import os
import threading
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve


LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.getenv("ICAR_LOCAL_PROXY_PORT", "8765"))
HTTP_PORT = int(os.getenv("ICAR_LOCAL_HTTP_PROXY_PORT", "8766"))
CAR_HOST = os.getenv("ICAR_CAR_HOST", "192.168.137.117")
CAR_PORT = int(os.getenv("ICAR_CAR_PORT", "6500"))
CAR_URL = f"ws://{CAR_HOST}:{CAR_PORT}/ws/control"
HTTP_ROUTES = {
    "/health",
    "/video_feed",
    "/yolo_video_feed",
    "/yolo_detailed_status",
}


class VisionProxyHandler(http.server.BaseHTTPRequestHandler):
    """Stream a small allowlist of car HTTP endpoints over loopback."""

    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        route = urlsplit(self.path).path
        if route not in HTTP_ROUTES:
            self._json_error(404, "unsupported proxy route")
            return

        connection = http.client.HTTPConnection(CAR_HOST, CAR_PORT, timeout=10)
        try:
            connection.request("GET", route, headers={"Connection": "close"})
            upstream = connection.getresponse()
            self.send_response(upstream.status)
            self.send_header(
                "Content-Type",
                upstream.getheader("Content-Type", "application/octet-stream"),
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            while chunk := upstream.read(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, http.client.HTTPException) as exc:
            self._json_error(502, f"car HTTP proxy failed: {exc}")
        finally:
            connection.close()

    def _json_error(self, status, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


async def relay(source, destination):
    async for message in source:
        await destination.send(message)


async def proxy(browser_socket):
    async with connect(CAR_URL, open_timeout=5) as car_socket:
        browser_to_car = asyncio.create_task(relay(browser_socket, car_socket))
        car_to_browser = asyncio.create_task(relay(car_socket, browser_socket))
        done, pending = await asyncio.wait(
            {browser_to_car, car_to_browser},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)


async def main():
    print(f"Local control proxy: ws://{LISTEN_HOST}:{LISTEN_PORT} -> {CAR_URL}")
    print(
        f"Local vision proxy:  http://{LISTEN_HOST}:{HTTP_PORT} "
        f"-> http://{CAR_HOST}:{CAR_PORT}"
    )
    http_server = http.server.ThreadingHTTPServer(
        (LISTEN_HOST, HTTP_PORT), VisionProxyHandler
    )
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    try:
        async with serve(proxy, LISTEN_HOST, LISTEN_PORT):
            await asyncio.get_running_loop().create_future()
    finally:
        http_server.shutdown()
        http_server.server_close()
        http_thread.join(timeout=1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
