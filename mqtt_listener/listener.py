import paho.mqtt.client as mqtt
import psycopg2
import json
from datetime import datetime, timezone
import os
import time
from utils.logging import setup_logger

logger = setup_logger("mqtt_listener")

# Database config
DB_HOST = os.getenv("PSQL_HOST", "database")
DB_PORT = int(os.getenv("PSQL_PORT", "5432"))
DB_USER = os.getenv("PSQL_USER", "mqtt")
DB_PASS = os.getenv("PSQL_PASS", "smartallotment2026")
DB_NAME = os.getenv("PSQL_DB", "sensors")

# MQTT config - FIXED: Use empty credentials from env
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "")  # Empty from your docker-compose
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")  # Empty from your docker-compose

def wait_for_db():
    """Wait for database readiness"""
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER, 
                password=DB_PASS, database=DB_NAME
            )
            conn.close()
            logger.info("Database ready")
            return True
        except Exception as e:
            logger.info(f"Waiting for database... {e}")
            time.sleep(5)

def wait_for_mqtt():
    """Wait for MQTT broker"""
    while True:
        try:
            test_client = mqtt.Client()
            if MQTT_USER:
                test_client.username_pw_set(MQTT_USER, MQTT_PASS)
            test_client.connect(MQTT_HOST, MQTT_PORT, 5)
            test_client.disconnect()
            logger.info("MQTT broker ready")
            return True
        except Exception as e:
            logger.info(f"Waiting for MQTT broker... {e}")
            time.sleep(5)

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, 
        password=DB_PASS, database=DB_NAME
    )

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT broker: {rc}")
    if rc == 0:
        client.subscribe("sensors/+/data")
        logger.info("Subscribed to sensors/+/data")
    else:
        logger.error(f"Connection failed with code {rc}")

def validate_sensor(conn, device_id: int, sensor_id: str, sensor_type: str) -> bool:
    """Check if sensor is registered and active for this device"""
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, active 
        FROM sensors 
        WHERE device_id = %s 
        AND sensor_name = %s 
        AND sensor_type = %s
    """, (device_id, sensor_id, sensor_type))
    
    result = cur.fetchone()
    cur.close()
    
    if not result:
        logger.warning(f"Sensor {sensor_id} ({sensor_type}) not registered for device_id={device_id}")
        return False
    
    sensor_db_id, active = result
    
    if not active:
        logger.warning(f"Sensor {sensor_id} is registered but inactive for device_id={device_id}")
        return False
    
    return True 

def activate_device_if_needed(conn, uid: str) -> int | None:
    cur = conn.cursor()

    cur.execute("SELECT id, active FROM devices WHERE uid = %s;", (uid,))
    row = cur.fetchone()

    if not row:
        logger.warning(f"Rejected unknown device UID={uid}")
        cur.close()
        return None

    device_db_id, active = row

    if not active:
        logger.info(f"First check-in for device {uid}, activating")
        cur.execute("""
            UPDATE devices
            SET active = TRUE,
                last_seen = NOW()
            WHERE id = %s;
        """, (device_db_id,))
    else:
        cur.execute("""
            UPDATE devices
            SET last_seen = NOW()
            WHERE id = %s;
        """, (device_db_id,))

    conn.commit()
    cur.close()
    return device_db_id

def on_message(client, userdata, msg):

    """
    Expected payload:
    {
        "device_uid": "device001",
        "sensors": [
            {"type": "moisture", "id": "soil-sensor-001", "value": 65},
            {"type": "moisture", "id": "soil-sensor-002", "value": 72},
            {"type": "temperature", "id": "temp-sensor-001", "value": 18.2},
            {"type": "light", "id": "light-sensor-001", "value": 450}
        ]
    }
    """
    try:
        data = json.loads(msg.payload.decode())
        logger.info(f"Received: {data} from {msg.topic}")
        
        conn = connect_db()

        # Extract UID
        device_uid = data['device_uid']

        if device_uid.endswith("UNKNOWN"):
            logger.error("Device has UNKNOWN serial, rejecting")
            return # ❌ Stop processing unknown devices

        # Validate + activate device
        device_db_id = activate_device_if_needed(conn, device_uid)
        if not device_db_id:
            conn.close()
            return  # ❌ Stop processing unknown devices

        cur = conn.cursor()

        # Track valid and rejected sensors
        valid_sensors = []
        rejected_sensors = []
        
        # Loop through all sensors in the payload
        for sensor in data.get('sensors', []):
            sensor_id = sensor['id']
            sensor_type = sensor['type']

            # Validate sensor registration
            if not validate_sensor(conn, device_db_id, sensor_id, sensor_type):
                rejected_sensors.append(f"{sensor_id} ({sensor_type})")
                continue  # Skip this sensor
            
            # Determine unit based on sensor type
            if sensor['type'] == 'moisture':
                sensor_unit = '%'
            elif sensor['type'] == 'temperature':
                sensor_unit = '°C'
            elif sensor['type'] == 'light':
                sensor_unit = 'lx'

            current_time = datetime.now(timezone.utc)

            cur.execute("""
                INSERT INTO sensor_data (
                    site_id,
                    device_id,
                    time,
                    sensor_id,
                    sensor_name,
                    sensor_type,
                    value,
                    unit
                )
                VALUES (
                    (SELECT site_id FROM devices WHERE id = %s),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                device_db_id,
                device_db_id,
                current_time,
                sensor_id,
                sensor_id,              # or a nicer name later
                sensor['type'],
                sensor['value'],
                sensor_unit
            ))  

            # Update last_value and last_seen in sensors table
            cur.execute("""
                UPDATE sensors
                SET last_value = %s,
                    last_seen = %s
                WHERE device_id = %s
                AND sensor_name = %s
                AND sensor_type = %s
            """, (sensor['value'], current_time, device_db_id, sensor_id, sensor_type))
            
            valid_sensors.append(sensor_id)                  
        
        conn.commit()
        cur.close()
        conn.close()

        # Log results
        if valid_sensors:
            logger.info(f"✅ Saved {len(valid_sensors)} sensors from {device_uid}: {', '.join(valid_sensors)}")
        if rejected_sensors:
            logger.warning(f"❌ Rejected {len(rejected_sensors)} unregistered sensors from {device_uid}: {', '.join(rejected_sensors)}")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    logger.info("Starting MQTT listener...")
    
    # Wait for dependencies
    wait_for_mqtt()
    wait_for_db()
    
    # Create client
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Connect and loop
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        logger.info("Starting MQTT event loop...")
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")