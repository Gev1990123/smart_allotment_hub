import os
import time
import requests
import logging

MOISTURE_THRESHOLD = float(os.getenv("MOISTURE_THRESHOLD", 40))
PUMP_RUN_SECONDS = float(os.getenv("PUMP_RUN_SECONDS", 5))
RUN_INTERVAL = int(os.getenv("RUN_INTERVAL", 60))
API_URL = os.getenv("API_URL", "http://api:8000")

logger = logging.getLogger("logic")
logging.basicConfig(level=logging.INFO)

while True:
    try:
        resp = requests.get(f"{API_URL}/latest/SA-NODE1")
        resp.raise_for_status()
        sensors = resp.json()
        moisture_values = [s['sensor_value'] for s in sensors if s['sensor_type'] == 'moisture']

        if moisture_values:
            avg_moisture = sum(moisture_values) / len(moisture_values)
            logger.info(f"Average soil moisture: {avg_moisture:.1f}%")

            if avg_moisture < MOISTURE_THRESHOLD:
                logger.info(f"Moisture below threshold ({MOISTURE_THRESHOLD}%), triggering pump for {PUMP_RUN_SECONDS}s")
                # send MQTT command to node
                # mqtt_client.publish(f"pump/SA-NODE1", {"action": "run", "seconds": PUMP_RUN_SECONDS})

    except Exception as e:
        logger.error(f"Logic loop error: {e}")

    time.sleep(RUN_INTERVAL)
