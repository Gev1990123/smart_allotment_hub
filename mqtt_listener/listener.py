#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import psycopg2
import json
from datetime import datetime, timezone
import os
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

def on_message(client, userdata, msg):

    """
    {
    "device_id": "device001",
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
        cur = conn.cursor()
        
        device_id = data.get('device_id', msg.topic.split('/')[1])
        # Loop through all sensors in the payload
        for sensor in data.get('sensors', []):
            sensor_id = f"{sensor['id']}" 
            current_time = datetime.now(timezone.utc)

            # Dynamic INSERT based on sensor type
            if sensor['type'] == 'temperature':
                cur.execute("""INSERT INTO sensor_data (time, device_id, sensor_id, sensor_type, value, unit) 
                            VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                            current_time, 
                            device_id, 
                            sensor_id, 
                            sensor['type'], 
                            sensor['value'], 
                            sensor.get('unit', 'C')))
            elif sensor['type'] == 'moisture':
                cur.execute("""INSERT INTO sensor_data (time, device_id, sensor_id, sensor_type, value, unit) 
                            VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                            current_time, 
                            device_id, 
                            sensor_id, 
                            sensor['type'], 
                            sensor['value'], 
                            sensor.get('unit', '%')))
            elif sensor['type'] == 'light':
                cur.execute("""INSERT INTO sensor_data (time, device_id, sensor_id, sensor_type, value, unit) 
                            VALUES (%s, %s, %s, %s, %s, %s)""",
                            (
                            current_time, 
                            device_id, 
                            sensor_id, 
                            sensor['type'], 
                            sensor['value'], 
                            sensor.get('unit', 'lux')))
                    
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Saved {len(data.get('sensors', []))} sensors from {device_id}")
        
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