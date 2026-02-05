from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from pydantic import BaseModel
from db import get_connection
import auth

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

class SiteCreate(BaseModel):
    site_code: str
    friendly_name: str | None = None

class SiteInfo(BaseModel):
    site_code: str
    friendly_name: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None
    role: str = "user"

# -------------------------
# Authentication Dependency
# -------------------------

async def get_current_user(session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """Dependency to get current authenticated user"""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user = auth.validate_session(session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    return user


async def get_optional_user(session_token: Optional[str] = Cookie(None)) -> Optional[Dict[str, Any]]:
    """Dependency to optionally get current user (for pages that work with or without auth)"""
    if not session_token:
        return None
    return auth.validate_session(session_token)

async def require_sys_admin(current_user: Dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency to require sys_admin role"""
    if current_user.get("role") != "sys_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.post("/api/auth/login")
async def login(request: Request, login_data: LoginRequest):
    """Login endpoint"""
    user = auth.authenticate_user(login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Get client info
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", None)
    
    # Create session
    session_token = auth.create_session(user["user_id"], client_ip, user_agent)
    
    response = JSONResponse(content={
        "message": "Login successful",
        "user": {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    })
    
    # Set session cookie (httponly for security)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return response

@app.post("/api/auth/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    """Logout endpoint"""
    if session_token:
        auth.delete_session(session_token)
    
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("session_token")
    
    return response

@app.get("/api/auth/me")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "username": current_user["username"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": current_user["role"]
    }


# ---------------------------------------------------------
# USER MANAGEMENT (Admin only)
# ---------------------------------------------------------

@app.post("/api/users/create")
async def create_user(user_data: UserCreate, admin: Dict = Depends(require_sys_admin)):
    """Create a new user (admin only)"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if username or email already exists
    cur.execute("""
        SELECT username FROM users WHERE username = %s OR email = %s;
    """, (user_data.username, user_data.email))
    
    if cur.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )
    
    # Hash password
    password_hash = auth.hash_password(user_data.password)
    
    # Insert user
    cur.execute("""
        INSERT INTO users (username, email, password_hash, full_name, role)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, username, email, full_name, role;
    """, (user_data.username, user_data.email, password_hash, user_data.full_name, user_data.role))
    
    new_user = cur.fetchone()
    conn.commit()
    conn.close()
    
    return {
        "user_id": new_user[0],
        "username": new_user[1],
        "email": new_user[2],
        "full_name": new_user[3],
        "role": new_user[4]
    }

@app.post("/api/users/{user_id}/assign-site/{site_id}")
async def assign_user_to_site(user_id: int, site_id: int, admin: Dict = Depends(require_sys_admin)):
    """Assign a user to a site (admin only)"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO user_site_assignments (user_id, site_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, site_id) DO NOTHING;
        """, (user_id, site_id))
        
        conn.commit()
        conn.close()
        
        return {"message": f"User {user_id} assigned to site {site_id}"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/users/{user_id}/unassign-site/{site_id}")
async def unassign_user_from_site(user_id: int, site_id: int, admin: Dict = Depends(require_sys_admin)):
    """Remove a user's access to a site (admin only)"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM user_site_assignments
        WHERE user_id = %s AND site_id = %s;
    """, (user_id, site_id))
    
    conn.commit()
    conn.close()
    
    return {"message": f"User {user_id} unassigned from site {site_id}"}

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
# GET LATEST READINGS FOR DEVICE (with auth)
# ---------------------------------------------------------
@app.get("/api/latest/{device_uid}")
def get_latest(device_uid: str, current_user: Dict = Depends(get_current_user)):
    """Get latest readings - requires authentication and device access"""

    # Check if user can access this device
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this device"
        )

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
# GET HISTORY FOR A DEVICE (with auth)
# ---------------------------------------------------------
@app.get("/api/history/{device_uid}")
def get_history(device_uid: str, hours: int = 24, current_user: Dict = Depends(get_current_user)):
    """Get device history - requires authentication and device access"""

    # Check if user can access this device
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
# LIST ALL UNIQUE DEVICES (filtered by user access)
# ---------------------------------------------------------
@app.get("/api/devices")
def list_devices(current_user: Dict = Depends(get_current_user)):
    """List devices - filtered by user's site access"""

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Get user's allowed sites
        allowed_sites = auth.get_user_site_access(current_user["user_id"])

        # sys_admin (empty allowed_sites) gets all devices
        if not allowed_sites:
            cur.execute("SELECT DISTINCT uid, name, site_id FROM devices WHERE uid IS NOT NULL ORDER BY uid;")
        else:
            # Regular users only see devices from their assigned sites
            placeholders = ','.join(['%s'] * len(allowed_sites))
            cur.execute(f"""
                SELECT DISTINCT uid, name, site_id 
                FROM devices 
                WHERE uid IS NOT NULL AND site_id IN ({placeholders})
                ORDER BY uid;
            """, allowed_sites)
        
        rows = cur.fetchall()
        devices = [{"uid": row[0], "name": row[1], "site_id": row[2]} for row in rows]

        print(f"Found devices for user {current_user['username']}: {devices}")
        
        conn.close()

        return {"devices": devices}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
    finally:
        if conn:
            conn.close

# ---------------------------------------------------------
# LIST ALL UNIQUE SITES
# ---------------------------------------------------------
@app.get("/api/sites")
def list_sites():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT site_code, friendly_name, id  FROM sites WHERE site_code IS NOT NULL ORDER BY site_code;")
        rows = cur.fetchall()
        sites = [{"site_code": row[0], "friendly_name": row[1], "id": row[2]} for row in rows]

        print(f"Found sites: {sites}")
        
        conn.close()

        return {"sites": sites}

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

# ----------------------------------
# REGISTER A NEW DEVICE (admin only)
# ----------------------------------
@app.post("/api/device/register", response_model=DeviceInfo)
def register_device(device: DeviceCreate, admin: Dict = Depends(require_sys_admin)):
    """Register a new device - admin only"""
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

# --------------------------------
# REGISTER A NEW SITE (admin only)
# --------------------------------
@app.post("/api/site/register", response_model=SiteInfo)
def register_site(site: SiteCreate, admin: Dict = Depends(require_sys_admin)):
    conn = get_connection()
    cur = conn.cursor()

    # Check if site already exists
    cur.execute("SELECT site_code, friendly_name FROM sites WHERE site_code = %s;", (site.site_code,))
    row = cur.fetchone()
    if row:
        conn.close()
        raise HTTPException(status_code=400, detail="Site already registered")

    cur.execute("""
        INSERT INTO sites (site_code, friendly_name)
        VALUES (%s, %s)
        RETURNING site_code, friendly_name;
    """, (site.site_code, site.friendly_name))

    new_site = cur.fetchone()
    conn.commit()
    conn.close()

    return {
        "site_code": new_site[0],
        "friendly_name": new_site[1],
    }

# ---------------------------------------------------------
# UI ROUTES (HTML Templates)
# ---------------------------------------------------------

@app.get("/login")
def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/")
def dashboard(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Dashboard - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user
    })

@app.get("/devices")
def devices_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Devices page - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("devices.html", {
        "request": request,
        "user": current_user
    })

@app.get("/sites")
def sites_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Sites page - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("sites.html", {
        "request": request,
        "user": current_user
    })

@app.get("/device/{device_id}")
def device_page(device_id: str, request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Individual device page - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # Check access
    if not auth.user_can_access_device(current_user["user_id"], device_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return templates.TemplateResponse(
        "device.html",
        {"request": request, "device_id": device_id, "user": current_user}
    )


@app.get("/site/{site_id}")
def site_page(site_id: int, request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Site page - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # Check access
    if not auth.user_can_access_site(current_user["user_id"], site_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return templates.TemplateResponse(
        "site.html",
        {"request": request, "site_id": site_id, "user": current_user}
    )
