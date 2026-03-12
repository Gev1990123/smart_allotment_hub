import os
import time
import requests
import json
import paho.mqtt.client as mqtt
from itertools import groupby
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
    Fetch per-sensor moisture status, then group by zone_name.
    Sensors in the same zone are averaged before thresholds are applied.
    Sensors with no zone keep individual evaluation (existing behaviour).
    Returns one status dict per logical unit (zone or lone sensor).
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
        raw_statuses = []
        
        for sensor in moisture_sensors:
            try:
                resp = requests.get(
                    f"{API_URL}/api/sensors/{sensor['id']}/moisture-status",
                    headers=headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    data["zone_name"] = sensor.get("zone_name")
                    data["sensor_name"] = sensor["sensor_name"]
                    raw_statuses.append(data)
                else:
                    logger.warning(f"moisture-status returned {resp.status_code} for sensor {sensor['id']}")
            except requests.RequestException as e:
                logger.error(f"Failed to fetch status for sensor {sensor['id']}: {e}")

        # ---- Zone averaging ------------------------------------------------
        # Split into zoned and unzoned sensors
        zoned   = [s for s in raw_statuses if s.get("zone_name")]
        unzoned = [s for s in raw_statuses if not s.get("zone_name")]

        results = list(unzoned) # unzoned sensors evaluated individually as before

                # Group zoned sensors by zone_name
        zoned_sorted = sorted(zoned, key=lambda s: s["zone_name"])
        for zone_name, group in groupby(zoned_sorted, key=lambda s: s["zone_name"]):
            members = list(group)
            values  = [s["value"] for s in members if s.get("value") is not None]

            if not values:
                continue

            avg_value = sum(values) / len(values)

            profiles = set(s["profile"] for s in members)
            if len(profiles) == 1:
                representative = members[0]
                moisture_min = representative["moisture_min"]
                moisture_max = representative["moisture_max"]
                profile_name = representative["profile"]
            else:
                logger.warning(
                    f"Zone '{zone_name}' has mixed profiles: {profiles}. "
                    f"Falling back to General profile."
                )
                try:
                    gp_resp = requests.get(
                        f"{API_URL}/api/plant-profiles", headers=headers, timeout=10
                    )
                    gp_resp.raise_for_status()
                    general = next(
                        (p for p in gp_resp.json().get("plant_profiles", []) if p["name"] == "General"),
                        {"moisture_min": 30, "moisture_max": 70}  # hard fallback if DB unreachable
                    )
                    moisture_min = general["moisture_min"]
                    moisture_max = general["moisture_max"]
                    profile_name = "General (mixed zone fallback)"
                except Exception as e:
                    logger.error(f"Could not fetch General profile for zone '{zone_name}': {e}. Using hardcoded defaults.")
                    moisture_min = 30
                    moisture_max = 70
                    profile_name = "General (hardcoded fallback)"

            if avg_value < moisture_min:
                zone_status = "too_dry"
            elif avg_value > moisture_max:
                zone_status = "too_wet"
            else:
                zone_status = "ok"

            sensor_ids = [s["sensor_id"] for s in members]
            sensor_names = [s["sensor_name"] for s in members]

            logger.info(
                f"  Zone '{zone_name}' [{profile_name}]: "
                f"avg={avg_value:.1f}% (raw: {[round(v,1) for v in values]}) "
                f"— status={zone_status} (range {moisture_min}–{moisture_max}%)"
            )

            results.append({
                "sensor_id": sensor_ids,       # list so pump logic can log all
                "sensor_name": f"zone:{zone_name}",
                "value": round(avg_value, 2),
                "unit": members[0].get("unit", "%"),
                "status": zone_status,
                "profile": profile_name,
                "moisture_min": moisture_min,
                "moisture_max": moisture_max,
                "zone_name": zone_name,
                "zone_members": sensor_names,
            })

        return results

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
