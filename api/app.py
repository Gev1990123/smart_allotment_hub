from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
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

# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
@app.get("/health")
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
@app.get("/latest/{device_id}")
def get_latest(device_id: str):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT DISTINCT ON (sensor_type) 
                   time, device_id, sensor_id, sensor_type, value, unit
            FROM sensor_data
            WHERE device_id = %s
            ORDER BY sensor_type, time DESC;
        """, (device_id,))

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return JSONResponse(status_code=404, content={"error": "No data found"})

        # Return ALL sensors from latest reading as array
        sensors = []
        for row in rows:
            sensors.append({
                "sensor_name": row[2],
                "sensor_value": float(row[4]),
                "unit": row[5],
                "sensor_type": row[3],
                "timestamp": row[0]
            })

        return sensors        

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------
# GET HISTORY FOR A DEVICE (using your new schema)
# ---------------------------------------------------------
@app.get("/history/{device_id}")
def get_history(device_id: str, hours: int = 24):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT time, device_id, sensor_id, sensor_type, value, unit
            FROM sensor_data
            WHERE device_id = %s
              AND time > NOW() - INTERVAL '%s hours'
            ORDER BY time ASC;
        """, (device_id, hours))

        raw_rows = cur.fetchall()
        conn.close()

        # MAP raw rows → frontend-expected objects
        rows = []
        for row in raw_rows:
            rows.append({
                "sensor_name": row[2],
                "timestamp": row[0],
                "sensor_value": row[4],
                "sensor_type": row[3],
                "unit": row[5]
            })
        
        return rows

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------
# LIST ALL UNIQUE DEVICES
# ---------------------------------------------------------
@app.get("/devices")
def list_devices():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT device_id FROM sensor_data WHERE device_id IS NOT NULL ORDER BY device_id;")
        rows = cur.fetchall()
        devices = [row[0] for row in rows]

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
@app.get("/sensors")
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


# ---------------------------------------------------------
# UI ROUTES (HTML Templates)
# ---------------------------------------------------------

@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
