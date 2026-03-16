from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from dependencies import get_current_user
from models import SensorRegister, SensorPlantAssign, SensorZoneAssign
from db import get_connection
import auth

router = APIRouter(prefix="/api/sensors", tags=["sensors"])

@router.get("/list")
async def list_sensors_managed(current_user: Dict = Depends(get_current_user)):
    """
    List sensors — sys_admin sees all, regular users see only their sites' sensors.
    Includes plant_profile_id and plant_profile_name for the frontend badge.
    """
    conn = get_connection()
    cur = conn.cursor()

    try:
        allowed_sites = auth.get_user_site_access(current_user["user_id"])

        if not allowed_sites:
            cur.execute("""
                SELECT
                    s.id, s.device_id, d.uid AS device_uid, s.sensor_name,
                    s.sensor_type, s.unit, s.active, s.last_value, s.last_seen,
                    s.notes, s.created_at, s.zone_name,
                    spa.variety_id,
                    COALESCE(pt.name || ' - ' || pv.name, 'Not Assigned') AS plant_profile_name,
                    pt.emoji,
                    pv.moisture_min, pv.moisture_max,
                    pv.light_min, pv.light_max,
                    pv.temp_min, pv.temp_max
                FROM sensors s
                JOIN devices d ON s.device_id = d.id
                LEFT JOIN sensor_plant_assignments spa ON spa.sensor_id = s.id
                LEFT JOIN plant_varieties pv ON pv.id = spa.variety_id
                LEFT JOIN plant_types pt ON pt.id = pv.plant_type_id
                ORDER BY d.uid, s.sensor_name;
            """)
        else:
            placeholders = ','.join(['%s'] * len(allowed_sites))
            cur.execute(f"""
                SELECT
                    s.id, s.device_id, d.uid AS device_uid, s.sensor_name,
                    s.sensor_type, s.unit, s.active, s.last_value, s.last_seen,
                    s.notes, s.created_at, s.zone_name,
                    spa.variety_id,
                    COALESCE(pt.name || ' - ' || pv.name, 'Not Assigned') AS plant_profile_name,
                    pt.emoji,
                    pv.moisture_min, pv.moisture_max,
                    pv.light_min, pv.light_max,
                    pv.temp_min, pv.temp_max
                FROM sensors s
                JOIN devices d ON s.device_id = d.id
                LEFT JOIN sensor_plant_assignments spa ON spa.sensor_id = s.id
                LEFT JOIN plant_varieties pv ON pv.id = spa.variety_id
                LEFT JOIN plant_types pt ON pt.id = pv.plant_type_id        
                WHERE d.site_id IN ({placeholders})
                ORDER BY d.uid, s.sensor_name;
            """, allowed_sites)

        rows = cur.fetchall()

        sensors = []
        for row in rows:
            sensors.append({
                "id": row[0],
                "device_id": row[1],
                "device_uid": row[2],
                "sensor_name": row[3],
                "sensor_type": row[4],
                "unit": row[5],
                "active": row[6],
                "last_value": float(row[7]) if row[7] is not None else None,
                "last_seen": row[8].isoformat() if row[8] else None,
                "notes": row[9],
                "created_at": row[10].isoformat() if row[10] else None,
                "zone_name": row[11],
                "plant_profile_id": row[12],
                "plant_profile_name": row[13],
            })

        cur.close()
        conn.close()

        return {"sensors": sensors}

    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register")
async def register_sensor(sensor_data: SensorRegister, current_user: Dict = Depends(get_current_user)):
    """Register a new sensor against a device the user has access to"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, site_id FROM devices WHERE uid = %s;", (sensor_data.device_uid,))
        device_row = cur.fetchone()

        if not device_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Device not found")

        device_id, site_id = device_row

        if not auth.user_can_access_device(current_user["user_id"], sensor_data.device_uid):
            conn.close()
            raise HTTPException(status_code=403, detail="You don't have access to this device")

        cur.execute("""
            SELECT id FROM sensors
            WHERE device_id = %s AND sensor_name = %s;
        """, (device_id, sensor_data.sensor_name))

        if cur.fetchone():
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Sensor '{sensor_data.sensor_name}' already exists for this device"
            )

        unit = sensor_data.unit
        if not unit:
            unit_map = {
                'moisture': '%',
                'temperature': '°C',
                'light': 'lx'
            }
            unit = unit_map.get(sensor_data.sensor_type, '')

        cur.execute("""
            INSERT INTO sensors (
                device_id, sensor_name, sensor_type, unit,
                active, notes, zone_name, created_at, registered_by
            )
            VALUES (%s, %s, %s, %s, TRUE, %s, %s, NOW(), %s)
            RETURNING id, sensor_name, sensor_type, unit, active, created_at;
        """, (
            device_id,
            sensor_data.sensor_name,
            sensor_data.sensor_type,
            unit,
            sensor_data.notes,
            sensor_data.zone_name,
            current_user["user_id"]
        ))

        new_sensor = cur.fetchone()
        conn.commit()
        conn.close()

        return {
            "message": "Sensor registered successfully",
            "sensor": {
                "id": new_sensor[0],
                "sensor_name": new_sensor[1],
                "sensor_type": new_sensor[2],
                "unit": new_sensor[3],
                "active": new_sensor[4],
                "created_at": new_sensor[5].isoformat() if new_sensor[5] else None
            }
        }

    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{sensor_id}/activate")
async def activate_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Mark a sensor as active so it appears in dashboards"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT s.id, d.uid as device_uid
            FROM sensors s
            JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))

        sensor = cur.fetchone()

        if not sensor:
            conn.close()
            raise HTTPException(status_code=404, detail="Sensor not found")

        if not auth.user_can_access_device(current_user["user_id"], sensor[1]):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")

        cur.execute("UPDATE sensors SET active = TRUE WHERE id = %s;", (sensor_id,))
        conn.commit()
        conn.close()

        return {"message": "Sensor activated successfully"}

    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{sensor_id}/deactivate")
async def deactivate_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Mark a sensor as inactive (hides it from dashboards without deleting data)"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT s.id, d.uid as device_uid
            FROM sensors s
            JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))

        sensor = cur.fetchone()

        if not sensor:
            conn.close()
            raise HTTPException(status_code=404, detail="Sensor not found")

        if not auth.user_can_access_device(current_user["user_id"], sensor[1]):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")

        cur.execute("UPDATE sensors SET active = FALSE WHERE id = %s;", (sensor_id,))
        conn.commit()
        conn.close()

        return {"message": "Sensor deactivated successfully"}

    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{sensor_id}/delete")
async def delete_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Permanently delete a sensor record — does NOT delete historical sensor_data rows"""
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT s.id, s.sensor_name, d.uid as device_uid
            FROM sensors s
            JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))

        sensor = cur.fetchone()

        if not sensor:
            conn.close()
            raise HTTPException(status_code=404, detail="Sensor not found")

        if not auth.user_can_access_device(current_user["user_id"], sensor[2]):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")

        cur.execute("DELETE FROM sensors WHERE id = %s;", (sensor_id,))
        conn.commit()
        conn.close()

        return {"message": f"Sensor '{sensor[1]}' deleted successfully"}

    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# Plant profile assignments (sensor-scoped)
# ---------------------------------------------------------

@router.put("/{sensor_id}/plant-profile")
async def assign_plant_profile(
    sensor_id: int,
    body: SensorPlantAssign,
    current_user: Dict = Depends(get_current_user)
):
    """Assign a plant variety to a moisture sensor"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check sensor exists and get device
        cur.execute("""
            SELECT s.id, s.sensor_type, d.uid
            FROM sensors s JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))
        sensor = cur.fetchone()

        if not sensor:
            raise HTTPException(status_code=404, detail="Sensor not found")
        if not auth.user_can_access_device(current_user["user_id"], sensor[2]):
            raise HTTPException(status_code=403, detail="Access denied")
        if sensor[1] != "moisture":
            raise HTTPException(status_code=400, detail="Plant profiles only apply to moisture sensors")

        # Check variety exists
        cur.execute("SELECT id FROM plant_varieties WHERE id = %s;", (body.variety_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Plant variety not found")

        # Assign variety (column renamed from plant_profile_id to variety_id)
        cur.execute("""
            INSERT INTO sensor_plant_assignments (sensor_id, variety_id, assigned_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (sensor_id) DO UPDATE
                SET variety_id = EXCLUDED.variety_id,
                    assigned_at = NOW(),
                    assigned_by = EXCLUDED.assigned_by;
        """, (sensor_id, body.variety_id, current_user["user_id"]))

        conn.commit()
        return {"message": "Plant variety assigned"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/{sensor_id}/plant-profile")
async def remove_plant_profile(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Remove plant variety from a sensor (reverts to General default)"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check sensor and access
        cur.execute("""
            SELECT d.uid FROM sensors s JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sensor not found")
        if not auth.user_can_access_device(current_user["user_id"], row[0]):
            raise HTTPException(status_code=403, detail="Access denied")

        # Delete assignment (sets to NULL, will use General defaults)
        cur.execute("DELETE FROM sensor_plant_assignments WHERE sensor_id = %s;", (sensor_id,))
        conn.commit()
        return {"message": "Plant variety removed — sensor will use General defaults"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/{sensor_id}/moisture-status")
async def sensor_moisture_status(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """
    Return current moisture reading + whether it's ok/too_dry/too_wet
    based on the assigned plant variety (falls back to General).
    Also returns light and temperature constraints if available.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.last_value, s.unit, d.uid,
                   pt.emoji,
                   COALESCE(pt.name || ' - ' || pv.name, gp.name) AS profile_name,
                   COALESCE(pv.moisture_min, gpv.moisture_min) AS moisture_min,
                   COALESCE(pv.moisture_max, gpv.moisture_max) AS moisture_max,
                   pv.light_min, pv.light_max,
                   pv.temp_min, pv.temp_max
            FROM sensors s
            JOIN devices d ON s.device_id = d.id
            LEFT JOIN sensor_plant_assignments spa ON spa.sensor_id = s.id
            LEFT JOIN plant_varieties pv ON pv.id = spa.variety_id
            LEFT JOIN plant_types pt ON pt.id = pv.plant_type_id
            LEFT JOIN plant_types gp ON gp.name = 'General'
            LEFT JOIN plant_varieties gpv ON gpv.plant_type_id = gp.id AND gpv.name = 'General'
            WHERE s.id = %s;
        """, (sensor_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Sensor not found")
        if not auth.user_can_access_device(current_user["user_id"], row[2]):
            raise HTTPException(status_code=403, detail="Access denied")

        (value, unit, device_uid, emoji, profile_name, 
         moisture_min, moisture_max, light_min, light_max, 
         temp_min, temp_max) = row

        if value is None:
            return {
                "status": "no_data",
                "profile": profile_name,
                "emoji": emoji
            }

        # Determine moisture status
        if value < float(moisture_min):
            moisture_status = "too_dry"
        elif value > float(moisture_max):
            moisture_status = "too_wet"
        else:
            moisture_status = "ok"

        return {
            "sensor_id": sensor_id,
            "value": float(value),
            "unit": unit,
            "status": moisture_status,
            "profile": profile_name,
            "emoji": emoji,
            "constraints": {
                "moisture": {
                    "min": float(moisture_min),
                    "max": float(moisture_max),
                    "status": moisture_status
                },
                "light": {
                    "min": float(light_min) if light_min else None,
                    "max": float(light_max) if light_max else None
                } if (light_min or light_max) else None,
                "temperature": {
                    "min": float(temp_min) if temp_min else None,
                    "max": float(temp_max) if temp_max else None
                } if (temp_min or temp_max) else None
            }
        }
    finally:
        conn.close()

@router.get("/{sensor_id}/moisture-events")
async def sensor_moisture_events(
    sensor_id: int,
    hours: int = 24,
    current_user: Dict = Depends(get_current_user)
):
    """History of moisture status events for a sensor"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check access
        cur.execute("""
            SELECT d.uid FROM sensors s JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sensor not found")
        if not auth.user_can_access_device(current_user["user_id"], row[0]):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get events
        cur.execute("""
            SELECT reading, expected_min, expected_max, status, action_taken, created_at
            FROM moisture_events
            WHERE sensor_id = %s
              AND created_at > NOW() - INTERVAL '%s hours'
            ORDER BY created_at DESC;
        """, (sensor_id, hours))

        rows = cur.fetchall()
        return {
            "sensor_id": sensor_id,
            "hours": hours,
            "events": [
                {
                    "reading": float(r[0]),
                    "expected_min": float(r[1]),
                    "expected_max": float(r[2]),
                    "status": r[3],
                    "action_taken": r[4],
                    "created_at": r[5].isoformat()
                }
                for r in rows
            ]
        }
    finally:
        conn.close()

# ---------------------------------------------------------
# Zones
# ---------------------------------------------------------

@router.put("/{sensor_id}/zone")
async def assign_sensor_zone(
    sensor_id: int,
    body: SensorZoneAssign,
    current_user: Dict = Depends(get_current_user)
):
    """Assign or clear a zone name on a sensor"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.id, d.uid FROM sensors s
            JOIN devices d ON s.device_id = d.id
            WHERE s.id = %s;
        """, (sensor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sensor not found")
        if not auth.user_can_access_device(current_user["user_id"], row[1]):
            raise HTTPException(status_code=403, detail="Access denied")

        cur.execute("UPDATE sensors SET zone_name = %s WHERE id = %s;", (body.zone_name, sensor_id))
        conn.commit()
        return {"message": f"Zone set to '{body.zone_name}'" if body.zone_name else "Zone cleared"}
    finally:
        conn.close()