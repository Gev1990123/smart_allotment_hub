from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from pydantic import BaseModel
from db import get_connection

app = FastAPI(title="Smart Allotment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static + templates (absolute paths inside the container)
app.mount("/static", StaticFiles(directory="/api/static"), name="static")
templates = Jinja2Templates(directory="/api/templates")

# -------------------------
# Pydantic models
# -------------------------
class DeviceCreate(BaseModel):
    uid: str
    name: str | None = None
    site_id: int | None = None

class DeviceInfo(BaseModel):
    uid: str
    name: str | None
    active: bool
    last_seen: str | None
    site_id: int | None

# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
@app.get("/api/health")
def health():
    try:
        conn = get_connection()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "details": str(e)})


# ---------------------------------------------------------
# GET LATEST READINGS FOR DEVICE
# ---------------------------------------------------------
@app.get("/api/latest/{device_uid}")
def get_latest(device_uid: str):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
                    SELECT DISTINCT ON (sd.sensor_type) 
                        d.uid as device_uid,
                        sd.sensor_name,
                        sd.value,
                        sd.unit,
                        sd.sensor_type, 
                        sd.time 
                    FROM devices d
                    INNER JOIN sensor_data sd ON d.id = sd.device_id
                    WHERE d.uid = %s
                    ORDER BY sd.sensor_type, sd.time DESC;
                """, (device_uid,))

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return JSONResponse(status_code=404, content={"error": "No data found"})

        # Return ALL sensors from latest reading as array
        sensors = []
        for row in rows:
            sensors.append({
                "sensor_name": row[1],
                "sensor_value": float(row[2]) if row[2] is not None else 0.0,
                "unit": row[3],
                "sensor_type": row[4],
                "timestamp": row[5]
            })

        return sensors        

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------
# GET HISTORY FOR A DEVICE
# ---------------------------------------------------------
@app.get("/api/history/{device_uid}")
def get_history(device_uid: str, hours: int = 24):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                d.uid as device_uid,
                sd.sensor_name,
                sd.time,
                sd.value,
                sd.sensor_type,
                sd.unit
            FROM devices d
            INNER JOIN sensor_data sd ON d.id = sd.device_id
            WHERE d.uid = %s
            AND sd.time > NOW() - INTERVAL '%s hours'
            ORDER BY sd.time ASC;""", 
            (device_uid, hours))

        raw_rows = cur.fetchall()
        conn.close()

        # MAP raw rows → frontend-expected objects
        rows = []
        for row in raw_rows:
            rows.append({
                "sensor_name": row[1],
                "timestamp": row[2],
                "sensor_value": row[3],
                "sensor_type": row[4],
                "unit": row[5]
            })
        
        return rows

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------
# LIST ALL UNIQUE DEVICES
# ---------------------------------------------------------
@app.get("/api/devices")
def list_devices():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT uid, name FROM devices WHERE uid IS NOT NULL ORDER BY uid;")
        rows = cur.fetchall()
        devices = [{"uid": row[0], "name": row[1]} for row in rows]

        print(f"Found devices: {devices}")
        
        conn.close()

        return {"devices": devices}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
    finally:
        if conn:
            conn.close

# ---------------------------------------------------------
# LIST ALL UNIQUE SENSORS
# ---------------------------------------------------------
@app.get("/api/sensors")
def list_sensors():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT sensor_id FROM sensor_data WHERE sensor_id IS NOT NULL ORDER BY sensor_id;")
        rows = cur.fetchall()
        sensors = [row[0] for row in rows]

        print(f"Found sensors: {sensors}")
        
        conn.close()

        return {"sensors": sensors}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
    finally:
        if conn:
            conn.close

# -------------------------
# REGISTER A NEW DEVICE
# -------------------------
@app.post("/api/device/register", response_model=DeviceInfo)
def register_device(device: DeviceCreate):
    conn = get_connection()
    cur = conn.cursor()

    # Check if device already exists
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


# ---------------------------------------------------------
# UI ROUTES (HTML Templates)
# ---------------------------------------------------------

@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/devices")
def devices_page(request: Request):
    return templates.TemplateResponse("devices.html", {"request": request})


@app.get("/device/{device_id}")
def device_page(device_id: str, request: Request):
    return templates.TemplateResponse(
        "device.html",
        {"request": request, "device_id": device_id}
    )


@app.get("/site/{site_id}")
def site_page(site_id: int, request: Request):
    return templates.TemplateResponse(
        "site.html",
        {"request": request, "site_id": site_id}
    )
