from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from typing import Dict
from datetime import datetime, timezone, timedelta
from dependencies import get_auth_user_or_token, require_sys_admin_dep, get_api_token_auth as get_api_token_auth_dep
from models import DeviceCreate, DeviceInfo, SensorDataSubmit, PumpCommand
from db import get_connection
import auth
import mqtt_publisher

router = APIRouter(prefix="/api", tags=["devices"])

@router.get("/health")
def health():
    """Simple liveness check — also verifies the DB connection is reachable"""
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "details": str(e)})

@router.get("/node_health/{device_uid}")
def node_health(device_uid: str, current_user: Dict = Depends(get_auth_user_or_token)):
    """Return node health status"""
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this device"
        )

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT last_seen FROM devices WHERE uid = %s", (device_uid,))
        row = cur.fetchone()

        if row is None:
            return {"status": "offline"}

        last_seen = row[0]

        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        is_online = last_seen and (now - last_seen) < timedelta(minutes=60)

        return {
            "status": "online" if is_online else "offline",
            "last_seen": last_seen.isoformat() if last_seen else None
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "details": str(e)})

@router.get("/latest/{device_uid}")
def get_latest(device_uid: str, current_user: Dict = Depends(get_auth_user_or_token)):
    """
    Return the most recent reading for each sensor type on a device.
    Results are averaged over a 30-second window around the latest timestamp.
    """
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this device"
        )

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            WITH latest_time AS (
                SELECT
                    sd.sensor_type,
                    max(sd.time) AS latest_time
                FROM devices d
                JOIN sensor_data sd ON d.id = sd.device_id
                WHERE d.uid = %s
                GROUP BY sd.sensor_type
            )
            SELECT
                d.uid          AS device_uid,
                sd.sensor_type,
                avg(sd.value)  AS avg_value,
                max(sd.unit)   AS unit
            FROM devices d
            JOIN sensor_data sd ON d.id = sd.device_id
            JOIN latest_time lt
            ON lt.sensor_type = sd.sensor_type
            WHERE d.uid = %s
            AND sd.time >= lt.latest_time - interval '30 seconds'
            GROUP BY d.uid, sd.sensor_type;
        """, (device_uid, device_uid))

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return JSONResponse(status_code=404, content={"error": "No data found"})

        sensors = []
        for row in rows:
            sensors.append({
                "sensor_value": float(row[2]) if row[2] is not None else 0.0,
                "unit": row[3],
                "sensor_type": row[1]
            })

        return sensors

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/history/{device_uid}")
def get_history(device_uid: str, hours: int = 24, current_user: Dict = Depends(get_auth_user_or_token)):
    """
    Return all readings for a device within the last N hours (default 24).
    Bucketed by hour; ordered oldest-first for charting.
    """
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this device"
        )

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                d.uid AS device_uid,
                sd.sensor_type,
                date_trunc('hour', sd.time) AS time_bucket,
                AVG(sd.value) AS avg_value,
                MIN(sd.unit) AS unit
            FROM devices d
            INNER JOIN sensor_data sd ON d.id = sd.device_id
            WHERE d.uid = %s
            AND sd.time > NOW() - INTERVAL '%s hours'
            GROUP BY d.uid, sd.sensor_type, date_trunc('hour', sd.time)
            ORDER BY time_bucket ASC;
        """, (device_uid, hours))

        raw_rows = cur.fetchall()
        conn.close()

        rows = []
        for row in raw_rows:
            rows.append({
                "sensor_name": row[1],
                "timestamp": row[2],
                "sensor_value": row[3],
                "sensor_type": row[1],
                "unit": row[4]
            })

        return rows

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/devices")
def list_devices(current_user: Dict = Depends(get_auth_user_or_token)):
    """
    List devices the current user can access.
    sys_admin sees all; regular users only see devices on their assigned sites.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        allowed_sites = auth.get_user_site_access(current_user["user_id"])

        if not allowed_sites:
            cur.execute("SELECT DISTINCT uid, name, site_id FROM devices WHERE uid IS NOT NULL ORDER BY uid;")
        else:
            placeholders = ','.join(['%s'] * len(allowed_sites))
            cur.execute(f"""
                SELECT DISTINCT uid, name, site_id
                FROM devices
                WHERE uid IS NOT NULL AND site_id IN ({placeholders})
                ORDER BY uid;
            """, allowed_sites)

        rows = cur.fetchall()
        devices = [{"uid": row[0], "name": row[1], "site_id": row[2]} for row in rows]

        conn.close()
        return {"devices": devices}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if conn:
            conn.close()

@router.post("/device/register", response_model=DeviceInfo)
def register_device(device: DeviceCreate, admin: Dict = Depends(require_sys_admin_dep)):
    """Register a new device — sys_admin only. Device starts inactive until it sends data."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT uid, name, active, last_seen, site_id FROM devices WHERE uid = %s;", (device.uid,))
    row = cur.fetchone()
    if row:
        conn.close()
        raise HTTPException(status_code=400, detail="Device already registered")

    cur.execute("""
        INSERT INTO devices (uid, name, site_id, active)
        VALUES (%s, %s, %s, FALSE)
        RETURNING uid, name, active, last_seen, site_id;
    """, (device.uid, device.name, device.site_id))

    new_device = cur.fetchone()
    conn.commit()
    conn.close()

    return {
        "uid": new_device[0],
        "name": new_device[1],
        "active": new_device[2],
        "last_seen": new_device[3],
        "site_id": new_device[4],
    }

@router.post("/data/submit")
async def submit_sensor_data(
    data: SensorDataSubmit,
    token_info: Dict = Depends(get_api_token_auth_dep),
):
    """
    Submit sensor data — device API token only.
    The device is identified by the token itself (not the request body),
    so a token can only ever write data for its own device.
    """
    if token_info["type"] != "device":
        raise HTTPException(status_code=403, detail="Device token required")

    if not auth.check_token_scope(token_info, "write:sensor_data"):
        raise HTTPException(status_code=403, detail="Token lacks write:sensor_data scope")

    device_uid = token_info["device_uid"]
    device_site_id = token_info["device_site_id"]

    if not device_site_id:
        raise HTTPException(status_code=400, detail="Device must be assigned to a site")

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM devices WHERE uid = %s;", (device_uid,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Device not found")

        device_id = row[0]

        cur.execute("""
            INSERT INTO sensor_data (site_id, device_id, sensor_name, value, unit, sensor_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (device_site_id, device_id, data.sensor_name, data.sensor_value, data.unit, data.sensor_type))

        data_id = cur.fetchone()[0]

        cur.execute("""
            UPDATE devices SET last_seen = NOW(), active = TRUE WHERE id = %s;
        """, (device_id,))

        conn.commit()
        conn.close()

        return {
            "message": "Data submitted successfully",
            "data_id": data_id,
            "device_uid": device_uid
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/devices/{device_uid}/read-now")
async def trigger_manual_reading(device_uid: str, current_user: Dict = Depends(get_auth_user_or_token)):
    """Send an MQTT command to trigger an immediate sensor reading on the device."""
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        mqtt_publisher.publish_command(
            device_uid=device_uid,
            command="read-now",
            extra={"requested_by": current_user["username"]}
        )
        return {"message": f"Read command sent to {device_uid}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/devices/{device_uid}/pump")
async def trigger_pump(device_uid: str, command: PumpCommand, current_user: Dict = Depends(get_auth_user_or_token)):
    """
    Send an MQTT pump command to a device — sys_admin only.
    Actions: 'on', 'off', 'run' (on for N seconds then auto-off).
    """
    if current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(status_code=403, detail="Access denied")

    if command.action not in ("on", "off", "run"):
        raise HTTPException(status_code=400, detail="Action must be 'on', 'off', or 'run'")

    if command.action == "run" and not command.seconds:
        raise HTTPException(status_code=400, detail="'run' action requires 'seconds'")

    try:
        mqtt_publisher.publish_command(
            device_uid=device_uid,
            command="pump",
            extra={
                "action": command.action,
                "seconds": command.seconds,
                "requested_by": current_user["username"]
            }
        )
        return {"message": f"Pump '{command.action}' command sent to {device_uid}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))