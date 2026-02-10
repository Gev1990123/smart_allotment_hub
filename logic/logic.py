import os
import time
import requests
import json
import logging
import sys
import paho.mqtt.client as mqtt
from utils.logging import setup_logger

# -------------------------
# Config from environment
# -------------------------
MOISTURE_THRESHOLD = float(40)
PUMP_RUN_SECONDS = float(5)
RUN_INTERVAL = int(60)
SKIP_INTERVAL = int(120)

API_URL = os.getenv("API_URL", "http://localhost:8000")
LOGIC_API_TOKEN=os.getenv("LOGIC_API_TOKEN", "default-token")

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

#DEVICE_ID = os.getenv("DEVICE_ID", "SA-NODE1")

# -------------------------
# Logging setup
# -------------------------
logger = setup_logger("logic")

# -------------------------
# MQTT client setup
# -------------------------
mqtt_client = mqtt.Client(client_id="logic-service")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        logger.error(f"MQTT connection failed with rc={rc}")

mqtt_client.on_connect = on_connect
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

# -------------------------
# Pump trigger helper
# -------------------------
def trigger_pump(node_id: str, seconds: float):
    topic = f"pump/{node_id}"
    payload = {"action": "run", "seconds": seconds}

    mqtt_client.publish(topic, json.dumps(payload), qos=1)
    logger.info(f"Published pump command to {topic}: {payload}")

# -------------------------
# Dynamic device fetcher
# -------------------------

def devices(headers):
    try:

        resp = requests.get(f"{API_URL}/api/devices", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Extract device UIDs
        devices_uids = [device["uid"] for device in data.get("devices", [])]

        return devices_uids
    except requests.RequestException as e:
        logger.error(f"Failed to fetch devices: {e}")
        return []

# -------------------------
# Main logic loop
# -------------------------
last_triggered = {}  # skip repeated triggers if moisture is still low

headers = {
            "Authorization": f"Bearer {LOGIC_API_TOKEN}",
            "Content-Type": "application/json"
        }

while True:
    try:
        for DEVICE_UID in devices(headers):
            logger.info(f"Processing device {DEVICE_UID}")


            # Get latest readings from API

            resp = requests.get(f"{API_URL}/api/latest/{DEVICE_UID}", headers=headers, timeout=10)
            resp.raise_for_status()
            sensors = resp.json()

            # Filter moisture sensors
            moisture_values = [s['sensor_value'] for s in sensors if s['sensor_type'] == 'moisture']

            if moisture_values:
                avg_moisture = sum(moisture_values) / len(moisture_values)
                logger.info(f"Average soil moisture: {avg_moisture:.1f}%")

                current_time = time.time()
                last_time = last_triggered.get(DEVICE_UID, 0)

                if avg_moisture < MOISTURE_THRESHOLD:
                    if current_time - last_time >= SKIP_INTERVAL:
                        logger.info(f"Moisture below threshold ({MOISTURE_THRESHOLD}%), triggering pump")
                        trigger_pump(DEVICE_UID, PUMP_RUN_SECONDS)
                        last_triggered[DEVICE_UID] = current_time
                    else:
                        remaining = SKIP_INTERVAL - (current_time - last_time)
                        logger.info(f"Moisture low but skipping pump for {remaining:.0f}s more")
                else:
                    logger.info(f"Moisture above threshold {MOISTURE_THRESHOLD}%, no action required")
                    last_triggered[DEVICE_UID] = 0
            else:
                logger.warning("No moisture sensors found in latest readings")

    except requests.RequestException as e:
        logger.error(f"HTTP/API error: {e}")
    except Exception as e:
        logger.error(f"Logic loop error: {e}")

    time.sleep(RUN_INTERVAL)