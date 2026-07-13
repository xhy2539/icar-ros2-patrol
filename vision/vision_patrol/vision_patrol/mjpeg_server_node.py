#!/usr/bin/env python3
"""Expose ROS camera topics as loopback-only MJPEG streams.

The Astra ROS driver remains the single camera owner.  HTTP clients consume
encoded copies of its raw or annotated image topics instead of opening the UVC
device a second time.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class MjpegServerNode(Node):
    def __init__(self):
        super().__init__("vision_mjpeg_server")
        self.declare_parameter("raw_topic", "/camera/color/image_raw")
        self.declare_parameter("annotated_topic", "/vision/annotated_image")
        self.declare_parameter("listen_host", "127.0.0.1")
        self.declare_parameter("listen_port", 6502)
        self.declare_parameter("jpeg_quality", 75)
        self.declare_parameter("stale_timeout_sec", 2.0)

        self._bridge = CvBridge()
        self._quality = int(self.get_parameter("jpeg_quality").value)
        self._stale_timeout = float(
            self.get_parameter("stale_timeout_sec").value
        )
        self._frames = {"raw": None, "annotated": None}
        self._updated = {"raw": 0.0, "annotated": 0.0}
        self._lock = threading.Lock()

        raw_topic = str(self.get_parameter("raw_topic").value)
        annotated_topic = str(self.get_parameter("annotated_topic").value)
        self.create_subscription(
            Image,
            raw_topic,
            lambda msg: self._on_image("raw", msg),
            qos_profile_sensor_data,
        )
        self.create_subscription(
            Image,
            annotated_topic,
            lambda msg: self._on_image("annotated", msg),
            qos_profile_sensor_data,
        )

        host = str(self.get_parameter("listen_host").value)
        port = int(self.get_parameter("listen_port").value)
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()
        self.get_logger().info(
            f"MJPEG server ready on http://{host}:{port}; "
            f"raw={raw_topic}; annotated={annotated_topic}"
        )

    def _on_image(self, kind, message):
        try:
            frame = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality]
            )
            if not ok:
                return
            with self._lock:
                self._frames[kind] = encoded.tobytes()
                self._updated[kind] = time.monotonic()
        except Exception as exc:  # pylint: disable=broad-except
            self.get_logger().warning(f"failed to encode {kind} image: {exc}")

    def _snapshot(self, kind):
        with self._lock:
            frame = self._frames[kind]
            updated = self._updated[kind]
        ready = frame is not None and time.monotonic() - updated <= self._stale_timeout
        return (frame if ready else None), ready, updated

    def status(self):
        _, raw_ready, _ = self._snapshot("raw")
        _, annotated_ready, _ = self._snapshot("annotated")
        return {
            "ready": raw_ready,
            "raw_ready": raw_ready,
            "annotated_ready": annotated_ready,
        }

    def _make_handler(self):
        node = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                route = self.path.split("?", 1)[0]
                if route == "/health":
                    body = json.dumps(node.status()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if route == "/video_feed":
                    self._stream("raw")
                    return
                if route == "/yolo_video_feed":
                    self._stream("annotated", fallback="raw")
                    return
                if route == "/snapshot":
                    self._send_snapshot("raw")
                    return
                if route == "/yolo_snapshot":
                    self._send_snapshot("annotated", fallback="raw")
                    return
                self.send_error(404)

            def _send_snapshot(self, kind, fallback=None):
                frame, ready, _ = node._snapshot(kind)
                if not ready and fallback:
                    frame, ready, _ = node._snapshot(fallback)
                if not ready:
                    body = b'{"error":"camera frame unavailable"}'
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(frame)

            def _stream(self, kind, fallback=None):
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                last_updated = 0.0
                try:
                    while rclpy.ok():
                        frame, ready, updated = node._snapshot(kind)
                        if not ready and fallback:
                            frame, ready, updated = node._snapshot(fallback)
                        if not ready or updated <= last_updated:
                            time.sleep(0.02)
                            continue
                        last_updated = updated
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                            + frame
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format, *args):
                return

        return Handler

    def destroy_node(self):
        self._server.shutdown()
        self._server.server_close()
        self._server_thread.join(timeout=1.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MjpegServerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
