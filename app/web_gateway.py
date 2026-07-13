"""HTTP/MJPEG and WebSocket gateway for the mobile app.

The ROS Astra driver is the single camera owner. Video is proxied from the
loopback-only vision MJPEG node; this process never opens a camera device or a
chassis serial port.
"""

import http.client
import json
import logging
import os
import socket
import threading

from flask import Flask, Response, jsonify, request, send_file
from flask_sock import Sock


LOG = logging.getLogger("icar.web_gateway")
BRIDGE_HOST = os.getenv("ICAR_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("ICAR_BRIDGE_PORT", "6501"))
WEB_PORT = int(os.getenv("ICAR_WEB_PORT", "6500"))
ROS_VIDEO_HOST = os.getenv("ICAR_ROS_VIDEO_HOST", "127.0.0.1")
ROS_VIDEO_PORT = int(os.getenv("ICAR_ROS_VIDEO_PORT", "6502"))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_SIMULATOR = os.path.join(PROJECT_ROOT, "web", "control_simulator.html")

app = Flask(__name__)
sock = Sock(app)


def _video_status() -> dict:
    connection = http.client.HTTPConnection(
        ROS_VIDEO_HOST, ROS_VIDEO_PORT, timeout=0.5
    )
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        if response.status != 200:
            return {"ready": False, "error": f"HTTP {response.status}"}
        payload = json.loads(response.read().decode("utf-8"))
        payload["source"] = "ros_mjpeg"
        payload["error"] = None if payload.get("ready") else "waiting for ROS image"
        return payload
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        return {"ready": False, "source": "ros_mjpeg", "error": str(exc)}
    finally:
        connection.close()


def _proxy_video(path: str):
    connection = http.client.HTTPConnection(
        ROS_VIDEO_HOST, ROS_VIDEO_PORT, timeout=3.0
    )
    try:
        connection.request("GET", path, headers={"Connection": "close"})
        upstream = connection.getresponse()
    except (OSError, http.client.HTTPException) as exc:
        connection.close()
        return jsonify(error="video unavailable", detail=str(exc)), 503

    if upstream.status != 200:
        body = upstream.read()
        connection.close()
        return Response(
            body,
            status=upstream.status,
            content_type=upstream.getheader("Content-Type", "application/json"),
        )

    content_type = upstream.getheader(
        "Content-Type", "multipart/x-mixed-replace; boundary=frame"
    )

    def generate():
        try:
            while chunk := upstream.read(64 * 1024):
                yield chunk
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()

    return Response(generate(), content_type=content_type)


@app.get("/")
def index():
    return jsonify(
        service="icar-web-gateway",
        control="/ws/control",
        video="/video_feed",
        snapshot="/snapshot",
        health="/health",
    )


@app.get("/control_simulator")
def control_simulator():
    """Serve the control page from the car so WebSocket access is same-origin."""
    if not os.path.isfile(CONTROL_SIMULATOR):
        return jsonify(error="control simulator is not installed"), 404
    return send_file(CONTROL_SIMULATOR, mimetype="text/html")


@app.get("/health")
def health():
    bridge_ready = False
    try:
        with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=0.2):
            bridge_ready = True
    except OSError:
        pass
    return jsonify(camera=_video_status(), bridge_ready=bridge_ready)


@app.get("/video_feed")
def video_feed():
    return _proxy_video("/video_feed")


@app.get("/yolo_video_feed")
def yolo_video_feed():
    return _proxy_video("/yolo_video_feed")


@app.get("/snapshot")
def snapshot():
    return _proxy_video("/snapshot")


@app.get("/yolo_snapshot")
def yolo_snapshot():
    return _proxy_video("/yolo_snapshot")


@app.get("/yolo_detailed_status")
def yolo_detailed_status():
    camera = _video_status()
    enabled = bool(camera.get("annotated_ready"))
    return jsonify(
        status="ready" if enabled else "waiting_for_annotated_image",
        enabled=enabled,
        camera=camera,
    )


@sock.route("/ws/control")
def control_socket(ws):
    peer = request.remote_addr
    LOG.info("WebSocket client connected: %s", peer)
    tcp = socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=2.0)
    tcp.settimeout(0.5)
    stopped = threading.Event()

    def relay_to_websocket():
        buffer = b""
        try:
            while not stopped.is_set():
                try:
                    chunk = tcp.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line:
                        ws.send(line.decode("utf-8", errors="replace"))
        except (OSError, ConnectionError) as exc:
            if not stopped.is_set():
                LOG.warning("bridge receive failed for %s: %s", peer, exc)
        finally:
            stopped.set()
            try:
                ws.close()
            except Exception:
                pass

    relay_thread = threading.Thread(target=relay_to_websocket, daemon=True)
    relay_thread.start()
    try:
        while not stopped.is_set():
            message = ws.receive()
            if message is None:
                break
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            # One WebSocket message is one command; newline frames it on TCP.
            tcp.sendall(message.strip().encode("utf-8") + b"\n")
    except (OSError, ConnectionError) as exc:
        LOG.warning("control connection failed for %s: %s", peer, exc)
    finally:
        stopped.set()
        # Belt-and-suspenders stop. The bridge watchdog also stops on EOF.
        try:
            tcp.sendall(b"stop\n")
        except OSError:
            pass
        try:
            tcp.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        tcp.close()
        relay_thread.join(timeout=1.0)
        LOG.info("WebSocket client disconnected: %s", peer)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("ICAR_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOG.info(
        "starting on :%d, bridge=%s:%d, ROS video=%s:%d",
        WEB_PORT,
        BRIDGE_HOST,
        BRIDGE_PORT,
        ROS_VIDEO_HOST,
        ROS_VIDEO_PORT,
    )
    app.run(host="0.0.0.0", port=WEB_PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
