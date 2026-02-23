import os
import json
import logging
import paho.mqtt.client as mqtt
from utils.logging import setup_logger

logger = setup_logger("mqtt_publisher")

# Read MQTT connection settings from environment variables,
# with sensible defaults for local/Docker development
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt") # Docker service name or IP
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883")) # Standard MQTT port
MQTT_USER = os.getenv("MQTT_USERNAME", "") # Empty = anonymous (broker must allow it)
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")

# Module-level persistent client — created once and reused for all publishes.
# This avoids opening a new connection on every HTTP request.
_client = mqtt.Client()

def connect():
    """Connect the persistent MQTT client. Called once on FastAPI startup."""
    if MQTT_USER:
        # Only set credentials if a username is configured;
        # some brokers reject anonymous connections if auth is required
        _client.username_pw_set(MQTT_USER, MQTT_PASS)

    _client.connect(MQTT_HOST, MQTT_PORT, 60) # 60s keepalive interval
    # loop_start() spins up a background thread that handles
    # reconnects and outgoing message queuing automatically
    _client.loop_start()

    logger.info(f"MQTT publisher connected to {MQTT_HOST}:{MQTT_PORT}")

def publish_command(device_uid: str, command: str, extra: dict = {}):
    """
    Publish a command to a specific device via MQTT.

    Topic routing:
      - pump commands  → pump/{device_uid}          (matches node's existing subscription)
      - all others     → cmd/{device_uid}/{command}  (e.g. cmd/.../read-now)
    """
    # Pump uses its own legacy topic format
    if command == "pump":
        # The node subscribed to pump/{uid} before the cmd/... pattern was introduced,
        # so we keep this topic to stay compatible with the existing node code
        topic = f"pump/{device_uid}"
    else:
        topic = f"cmd/{device_uid}/{command}"

    # Merge the command name with any extra fields (e.g. action, seconds, requested_by)
    # into a single JSON payload
    payload = json.dumps({"command": command, **extra})

    # QoS 1 = at-least-once delivery; the broker will retry until the node ACKs it
    _client.publish(topic, payload, qos=1)
    logger.info(f"Published {topic}: {payload}")