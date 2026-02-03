import os
import time
import requests
import logging
import json
import paho.mqtt.client as mqtt


# -------------------------
# Config from environment
# -------------------------
MOISTURE_THRESHOLD = float(os.getenv("MOISTURE_THRESHOLD", 40))
PUMP_RUN_SECONDS = float(os.getenv("PUMP_RUN_SECONDS", 5))
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", 60))
API_URL = os.getenv("API_URL", "http://api:8000")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

logger = logging.getLogger("logic")
logging.basicConfig(level=logging.INFO)

# -------------------------
# MQTT publish helper
# -------------------------
def trigger_pump(node_id: str, seconds: float):
    topic = f"pump/{node_id}"
    payload = {"action": "run", "seconds": seconds}

    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    client.publish(topic, json.dumps(payload), qos=1)
    time.sleep(1)  # allow MQTT to send
    client.loop_stop()
    client.disconnect()
    logger.info(f"Sent pump command to {node_id} for {seconds}s")

# -------------------------
# Logic loop
# -------------------------
while True:
    try:
        # get latest readings from API
        resp = requests.get(f"{API_URL}/latest/SA-NODE1")
        resp.raise_for_status()
        sensors = resp.json()

        # filter moisture sensors
        moisture_values = [s['sensor_value'] for s in sensors if s['sensor_type'] == 'moisture']

        if moisture_values:
            avg_moisture = sum(moisture_values) / len(moisture_values)
            logger.info(f"Average soil moisture: {avg_moisture:.1f}%")

            if avg_moisture < MOISTURE_THRESHOLD:
                logger.info(f"Moisture below threshold ({MOISTURE_THRESHOLD}%), triggering pump for {PUMP_RUN_SECONDS}s")
                trigger_pump("SA-NODE1", PUMP_RUN_SECONDS)
            else:
                logger.info("Moisture above threshold, no action required")
        else:
            logger.warning("No moisture sensors found in latest readings")

    except Exception as e:
        logger.error(f"Logic loop error: {e}")

    time.sleep(RUN_INTERVAL)