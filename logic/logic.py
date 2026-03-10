import os
import time
import requests
import json
import paho.mqtt.client as mqtt
from utils.logging import setup_logger

# -------------------------
# Config from environment
# -------------------------
PUMP_RUN_SECONDS = float(os.getenv("PUMP_RUN_SECONDS", 5))
RUN_INTERVAL     = int(os.getenv("RUN_INTERVAL", 3600))
SKIP_INTERVAL    = int(os.getenv("SKIP_INTERVAL", 3600))

# REMOVED: MOISTURE_THRESHOLD = float(40)
# Thresholds now come from plant profiles in the database via the API.
# Each sensor can have a different threshold depending on what's growing.

API_URL          = os.getenv("API_URL", "http://localhost:8000")
LOGIC_API_TOKEN  = os.getenv("LOGIC_API_TOKEN", "default-token")

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USERNAME", "")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")

# -------------------------
# Logging
# -------------------------
logger = setup_logger("logic")

# -------------------------
# MQTT client setup
# -------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        logger.error(f"MQTT connection failed with rc={rc}")

mqtt_client = mqtt.Client(client_id="logic-service")
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.on_connect = on_connect
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

# -------------------------
# Pump trigger
# -------------------------

def trigger_pump(node_id: str, seconds: float):
    topic = f"pump/{node_id}"
    payload = {"action": "run", "seconds": seconds}
    mqtt_client.publish(topic, json.dumps(payload), qos=1)
    logger.info(f"Published pump command to {topic}: {payload}")

# -------------------------
# Device fetcher
# -------------------------

def get_devices(headers: dict) -> list[str]:
    """Return list of device UIDs the logic service can access"""
    try:
        resp = requests.get(f"{API_URL}/api/devices", headers=headers, timeout=10)
        resp.raise_for_status()
        return [d["uid"] for d in resp.json().get("devices", [])]
    except requests.RequestException as e:
        logger.error(f"Failed to fetch devices: {e}")
        return []

# -------------------------
# Plant-profile-aware moisture check
# -------------------------

def get_moisture_statuses(device_uid: str, headers: dict) -> list[dict]:
    """
    Fetch per-sensor moisture status for a device.
    Each status includes:
      - sensor_id, value, unit
      - status: 'ok' | 'too_dry' | 'too_wet'
      - profile: plant profile name (e.g. 'Tomato', 'General')
      - moisture_min / moisture_max from that profile

    Falls back to 'General' profile if no profile is assigned to the sensor.
    Returns empty list on error.
    """
    try:
        # Get all sensors for this device
        resp = requests.get(f"{API_URL}/api/sensors/list", headers=headers, timeout=10)
        resp.raise_for_status()
        all_sensors = resp.json().get("sensors", [])

        # Filter: active moisture sensors on this device only
        moisture_sensors = [
            s for s in all_sensors
            if s["device_uid"] == device_uid
            and s["sensor_type"] == "moisture"
            and s["active"]
        ]

        if not moisture_sensors:
            return []

        # Fetch status for each sensor individually
        statuses = []
        for sensor in moisture_sensors:
            try:
                resp = requests.get(
                    f"{API_URL}/api/sensors/{sensor['id']}/moisture-status",
                    headers=headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    statuses.append(resp.json())
                else:
                    logger.warning(f"moisture-status returned {resp.status_code} for sensor {sensor['id']}")
            except requests.RequestException as e:
                logger.error(f"Failed to fetch status for sensor {sensor['id']}: {e}")

        return statuses

    except requests.RequestException as e:
        logger.error(f"Failed to fetch sensor list for {device_uid}: {e}")
        return []

# -------------------------
# Main logic loop
# -------------------------

last_triggered: dict[str, float] = {}  # device_uid → timestamp of last pump trigger

headers = {
    "Authorization": f"Bearer {LOGIC_API_TOKEN}",
    "Content-Type": "application/json"
}

while True:
    try:
        for device_uid in get_devices(headers):
            logger.info(f"Processing device {device_uid}")

            statuses = get_moisture_statuses(device_uid, headers)

            if not statuses:
                logger.warning(f"No active moisture sensors found for {device_uid}")
                continue

            # Log all sensor statuses for visibility
            for s in statuses:
                logger.info(
                    f"  Sensor {s['sensor_id']} [{s['profile']}]: "
                    f"{s['value']}% — status={s['status']} "
                    f"(range {s['moisture_min']}–{s['moisture_max']}%)"
                )

            dry_sensors = [s for s in statuses if s["status"] == "too_dry"]

            if dry_sensors:
                current_time = time.time()
                last_time = last_triggered.get(device_uid, 0)

                if current_time - last_time >= SKIP_INTERVAL:
                    # Log exactly which sensors triggered this and why
                    for s in dry_sensors:
                        logger.warning(
                            f"💧 {device_uid} sensor {s['sensor_id']} too dry: "
                            f"{s['value']}% < {s['moisture_min']}% [{s['profile']}]"
                        )
                    trigger_pump(device_uid, PUMP_RUN_SECONDS)
                    last_triggered[device_uid] = current_time
                else:
                    remaining = SKIP_INTERVAL - (current_time - last_time)
                    logger.info(
                        f"Moisture low on {device_uid} but skipping pump "
                        f"for {remaining:.0f}s more (debounce)"
                    )
            else:
                logger.info(f"✅ All moisture sensors within plant profile thresholds for {device_uid}")
                last_triggered[device_uid] = 0

    except requests.RequestException as e:
        logger.error(f"HTTP/API error: {e}")
    except Exception as e:
        logger.error(f"Logic loop error: {e}")

    time.sleep(RUN_INTERVAL)
