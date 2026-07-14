#!/bin/bash
# Auto-restarting MQTT bridge wrapper
cd "$(dirname "$0")/.."
while true; do
  python3 -u scripts/ws_mqtt_bridge.py
  echo "$(date): bridge exited, restarting in 3s..."
  sleep 3
done
