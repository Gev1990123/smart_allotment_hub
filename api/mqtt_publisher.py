import os
import json
import logging
import paho.mqtt.client as mqtt
from utils.logging import setup_logger

logger = setup_logger("mqtt_publisher")

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")

_client = mqtt.Client()

def connect():
    if MQTT_USER:
        _client.username_pw_set(MQTT_USER, MQTT_PASS)
    _client.connect(MQTT_HOST, MQTT_PORT, 60)
    _client.loop_start()
    logger.info(f"MQTT publisher connected to {MQTT_HOST}:{MQTT_PORT}")

def publish_command(device_uid: str, command: str, extra: dict = {}):
    """Publish a command to a device via MQTT."""
    # Pump uses its own legacy topic format
    if command == "pump":
        topic = f"pump/{device_uid}"
    else:
        topic = f"cmd/{device_uid}/{command}"

    payload = json.dumps({"command": command, **extra})
    _client.publish(topic, payload, qos=1)
    logger.info(f"Published {topic}: {payload}")
