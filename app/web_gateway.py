"""HTTP/MJPEG and WebSocket gateway for the mobile app.

This process deliberately does not import Rosmaster_Lib or open a chassis serial
device.  Chassis control belongs exclusively to the ROS 2 driver.
"""

import logging
import os
import socket
import threading
import time
from typing import Optional

import cv2
from flask import Flask, Response, jsonify, request, send_file
from flask_sock import Sock


LOG = logging.getLogger("icar.web_gateway")
CAMERA_DEVICE = os.getenv("ICAR_CAMERA_DEVICE", "/dev/camera_depth")
BRIDGE_HOST = os.getenv("ICAR_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("ICAR_BRIDGE_PORT", "6501"))
WEB_PORT = int(os.getenv("ICAR_WEB_PORT", "6500"))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTROL_SIMULATOR = os.path.join(PROJECT_ROOT, "web", "control_simulator.html")

app = Flask(__name__)
sock = Sock(app)


class CameraStream:
    def __init__(self, device: str) -> None:
        self.device = device
        self._frame: Optional[bytes] = None
        self._last_frame_at = 0.0
        self._error = "camera has not started"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
            if not capture.isOpened():
                self._set_error(f"cannot open {self.device}")
                capture.release()
                self._stop.wait(1.0)
                continue

            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            capture.set(cv2.CAP_PROP_FPS, 15)
            self._set_error("")
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    self._set_error(f"read failed for {self.device}")
                    break
                ok, encoded = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
                )
                if ok:
                    with self._lock:
                        self._frame = encoded.tobytes()
                        self._last_frame_at = time.monotonic()
            capture.release()
            self._stop.wait(0.5)

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._error = message

    def snapshot(self) -> Optional[bytes]:
        with self._lock:
            if time.monotonic() - self._last_frame_at > 2.0:
                return None
            return self._frame

    def status(self) -> dict:
        with self._lock:
            age = time.monotonic() - self._last_frame_at
            return {
                "device": self.device,
                "ready": self._frame is not None and age <= 2.0,
                "frame_age_sec": round(age, 3) if self._frame else None,
                "error": self._error or None,
            }


camera = CameraStream(CAMERA_DEVICE)


def _mjpeg_frames():
    while True:
        frame = camera.snapshot()
        if frame is None:
            time.sleep(0.1)
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(1.0 / 15.0)


@app.get("/")
def index():
    return jsonify(
        service="icar-web-gateway",
        control="/ws/control",
        video="/video_feed",
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
    return jsonify(camera=camera.status(), bridge_ready=bridge_ready)


@app.get("/video_feed")
def video_feed():
    if not camera.status()["ready"]:
        return jsonify(error="camera unavailable", camera=camera.status()), 503
    return Response(
        _mjpeg_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/yolo_video_feed")
def yolo_video_feed():
    # Until the ROS annotated-image bridge is wired in, return the live camera
    # instead of leaving clients waiting forever for a first frame.
    return video_feed()


@app.get("/yolo_detailed_status")
def yolo_detailed_status():
    return jsonify(status="disabled", enabled=False, camera=camera.status())


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
    camera.start()
    LOG.info(
        "starting on :%d, bridge=%s:%d, camera=%s",
        WEB_PORT,
        BRIDGE_HOST,
        BRIDGE_PORT,
        CAMERA_DEVICE,
    )
    # Flask-Sock's simple-websocket backend uses a real reader thread. The
    # threaded Werkzeug server keeps that model compatible with the camera
    # capture thread; gevent sockets can otherwise raise cross-thread errors.
    app.run(host="0.0.0.0", port=WEB_PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
