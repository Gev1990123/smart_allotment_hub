import os
import time
import requests
import logging
import json
import paho.mqtt.client as mqtt
import sys


# -------------------------
# Config from environment
# -------------------------
MOISTURE_THRESHOLD = float(os.getenv("MOISTURE_THRESHOLD", 40))
PUMP_RUN_SECONDS = float(os.getenv("PUMP_RUN_SECONDS", 5))
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", 60))

API_URL = os.getenv("API_URL", "http://api:8000")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

DEVICE_ID = "SA-NODE1"


logger = logging.getLogger("logic")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# -------------------------
# MQTT publish helper
# -------------------------

mqtt_client = mqtt.Client(client_id="logic-service")

def on_connect(client, userdata, flags, rc):
    logger.info(f"Logic MQTT connected with rc={rc}")

def on_publish(client, userdata, mid):
    logger.info(f"Logic MQTT publish confirmed mid={mid}")

mqtt_client.on_connect = on_connect
mqtt_client.on_publish = on_publish

logger.info(f"Connecting to MQTT at {MQTT_HOST}:{MQTT_PORT}")
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

# -------------------------
# Logic loop
# -------------------------
while True:
    try:
        resp = requests.get(f"{API_URL}/latest/{DEVICE_ID}")
        resp.raise_for_status()
        sensors = resp.json()

        moisture_values = [
            s['sensor_value']
            for s in sensors
            if s['sensor_type'] == 'moisture'
        ]

        if moisture_values:
            avg_moisture = sum(moisture_values) / len(moisture_values)
            logger.info(f"Average soil moisture: {avg_moisture:.1f}%")

            if avg_moisture < MOISTURE_THRESHOLD:
                logger.info(
                    f"Moisture below threshold ({MOISTURE_THRESHOLD}%), "
                    f"triggering pump for {PUMP_RUN_SECONDS}s"
                )

                topic = f"pump/{DEVICE_ID}"
                payload = {"action": "run", "seconds": PUMP_RUN_SECONDS}

                mqtt_client.publish(topic, json.dumps(payload), qos=1)
                logger.info(f"Published pump command to {topic}: {payload}")

            else:
                logger.info("Moisture above threshold, no action required")

        else:
            logger.warning("No moisture sensors found in latest readings")

    except Exception as e:
        logger.error(f"Logic loop error: {e}")

    time.sleep(RUN_INTERVAL)