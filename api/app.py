from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie, Header
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

class ApiTokenCreate(BaseModel):
    name: str
    description: str | None = None
    scopes: list[str] = []
    expires_days: int | None = None
    device_uid: str | None = None  # For device tokens

class SensorDataSubmit(BaseModel):
    sensor_name: str
    sensor_value: float
    unit: str | None = None
    sensor_type: str | None = None

class SensorRegister(BaseModel):
    device_uid: str
    sensor_name: str
    sensor_type: str
    unit: str | None = None
    notes: str | None = None

class SensorInfo(BaseModel):
    id: int
    device_id: int
    device_uid: str
    sensor_name: str
    sensor_type: str
    unit: str | None
    active: bool
    last_value: float | None
    last_seen: str | None
    notes: str | None
    created_at: str | None

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

async def get_api_token_auth(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Dependency to authenticate via API token (from Authorization header)"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Expected format: "Bearer {token}" or just "{token}"
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    
    token_info = auth.validate_api_token(token)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return token_info

async def get_auth_user_or_token(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Dependency to accept either session cookie OR API token
    Tries session first, then API token
    """
    # Try session cookie first
    if session_token:
        user = auth.validate_session(session_token)
        if user:
            user["auth_type"] = "session"
            return user
    
    # Try API token
    if authorization:
        token = authorization
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        
        token_info = auth.validate_api_token(token)
        if token_info:
            token_info["auth_type"] = "api_token"
            return token_info
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (session or API token)"
    )

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
# API TOKEN MANAGEMENT
# ---------------------------------------------------------

@app.post("/api/tokens/create")
async def create_token(token_data: ApiTokenCreate, current_user: Dict = Depends(get_current_user)):
    """Create a new API token (for current user or device)"""
    
    user_id = None
    device_id = None
    
    # If device_uid provided, this is a device token (admin only)
    if token_data.device_uid:
        if current_user.get("role") != "sys_admin":
            raise HTTPException(status_code=403, detail="Only admins can create device tokens")
        
        # Get device ID from UID
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE uid = %s;", (token_data.device_uid,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        device_id = row[0]
    else:
        # User token
        user_id = current_user["user_id"]
    
    try:
        token = auth.create_api_token(
            name=token_data.name,
            user_id=user_id,
            device_id=device_id,
            description=token_data.description,
            scopes=token_data.scopes,
            expires_days=token_data.expires_days,
            created_by=current_user["user_id"]
        )
        
        return {
            "message": "Token created successfully",
            "token": token["token"],  # Only shown once!
            "id": token["id"],
            "name": token["name"],
            "scopes": token["scopes"],
            "expires_at": token["expires_at"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tokens/list")
async def list_my_tokens(current_user: Dict = Depends(get_current_user)):
    """List current user's API tokens"""
    tokens = auth.list_user_tokens(current_user["user_id"])
    
    # Don't return actual token values, just metadata
    return {"tokens": tokens}


@app.delete("/api/tokens/{token_id}/revoke")
async def revoke_token(token_id: int, current_user: Dict = Depends(get_current_user)):
    """Revoke (deactivate) an API token"""
    
    # Verify token belongs to current user or user is admin
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT token, user_id FROM api_tokens WHERE id = %s;
    """, (token_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    
    token_value, token_user_id = row
    
    # Check ownership or admin
    if token_user_id != current_user["user_id"] and current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Not authorized to revoke this token")
    
    success = auth.revoke_api_token(token_value)
    
    if success:
        return {"message": "Token revoked successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to revoke token")

@app.post("/api/data/submit")
async def submit_sensor_data(
    data: SensorDataSubmit,
    token_info: Dict = Depends(get_api_token_auth)
):
    """Submit sensor data (API token only - typically from IoT devices)"""
    
    # Verify this is a device token
    if token_info["type"] != "device":
        raise HTTPException(status_code=403, detail="Device token required")
    
    # Check scope
    if not auth.check_token_scope(token_info, "write:sensor_data"):
        raise HTTPException(status_code=403, detail="Token lacks write:sensor_data scope")
    
    device_uid = token_info["device_uid"]
    device_site_id = token_info["device_site_id"]
    
    if not device_site_id:
        raise HTTPException(status_code=400, detail="Device must be assigned to a site")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Get device ID
        cur.execute("SELECT id FROM devices WHERE uid = %s;", (device_uid,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Device not found")
        
        device_id = row[0]
        
        # Insert sensor data
        cur.execute("""
            INSERT INTO sensor_data (site_id, device_id, sensor_name, value, unit, sensor_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (device_site_id, device_id, data.sensor_name, data.sensor_value, data.unit, data.sensor_type))
        
        data_id = cur.fetchone()[0]
        
        # Update device last_seen
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
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))

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
def get_latest(device_uid: str, current_user: Dict = Depends(get_auth_user_or_token)):
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
def get_history(device_uid: str, hours: int = 24, current_user: Dict = Depends(get_auth_user_or_token)):
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
def list_devices(current_user: Dict = Depends(get_auth_user_or_token)):
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
# SENSOR MANAGEMENT ENDPOINTS
# ---------------------------------------------------------

@app.get("/api/sensors/list")
async def list_sensors(current_user: Dict = Depends(get_current_user)):
    """List all sensors (filtered by user's site access)"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get user's allowed sites
        allowed_sites = auth.get_user_site_access(current_user["user_id"])
        
        # sys_admin gets all sensors
        if not allowed_sites:
            cur.execute("""
                SELECT 
                    s.id, s.device_id, d.uid as device_uid, s.sensor_name, 
                    s.sensor_type, s.unit, s.active, s.last_value, s.last_seen, 
                    s.notes, s.created_at
                FROM sensors s
                JOIN devices d ON s.device_id = d.id
                ORDER BY d.uid, s.sensor_name;
            """)
        else:
            # Regular users only see sensors from their assigned sites
            placeholders = ','.join(['%s'] * len(allowed_sites))
            cur.execute(f"""
                SELECT 
                    s.id, s.device_id, d.uid as device_uid, s.sensor_name, 
                    s.sensor_type, s.unit, s.active, s.last_value, s.last_seen, 
                    s.notes, s.created_at
                FROM sensors s
                JOIN devices d ON s.device_id = d.id
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
                "created_at": row[10].isoformat() if row[10] else None
            })
        
        cur.close()
        conn.close()
        
        return {"sensors": sensors}
        
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sensors/register")
async def register_sensor(
    sensor_data: SensorRegister, 
    current_user: Dict = Depends(get_current_user)
):
    """Register a new sensor (admin or device owner)"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get device ID from UID
        cur.execute("""
            SELECT id, site_id FROM devices WHERE uid = %s;
        """, (sensor_data.device_uid,))
        
        device_row = cur.fetchone()
        
        if not device_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Device not found")
        
        device_id, site_id = device_row
        
        # Check if user can access this device
        if not auth.user_can_access_device(current_user["user_id"], sensor_data.device_uid):
            conn.close()
            raise HTTPException(
                status_code=403, 
                detail="You don't have access to this device"
            )
        
        # Check if sensor already exists for this device
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
        
        # Auto-determine unit if not provided
        unit = sensor_data.unit
        if not unit:
            unit_map = {
                'moisture': '%',
                'temperature': '°C',
                'light': 'lx'
            }
            unit = unit_map.get(sensor_data.sensor_type, '')
        
        # Insert sensor
        cur.execute("""
            INSERT INTO sensors (
                device_id, sensor_name, sensor_type, unit, 
                active, notes, created_at, registered_by
            )
            VALUES (%s, %s, %s, %s, TRUE, %s, NOW(), %s)
            RETURNING id, sensor_name, sensor_type, unit, active, created_at;
        """, (
            device_id, 
            sensor_data.sensor_name, 
            sensor_data.sensor_type, 
            unit, 
            sensor_data.notes,
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


@app.post("/api/sensors/{sensor_id}/activate")
async def activate_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Activate a sensor"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get sensor info
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
        
        device_uid = sensor[1]
        
        # Check access
        if not auth.user_can_access_device(current_user["user_id"], device_uid):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Activate sensor
        cur.execute("""
            UPDATE sensors 
            SET active = TRUE 
            WHERE id = %s;
        """, (sensor_id,))
        
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


@app.post("/api/sensors/{sensor_id}/deactivate")
async def deactivate_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Deactivate a sensor"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get sensor info
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
        
        device_uid = sensor[1]
        
        # Check access
        if not auth.user_can_access_device(current_user["user_id"], device_uid):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Deactivate sensor
        cur.execute("""
            UPDATE sensors 
            SET active = FALSE 
            WHERE id = %s;
        """, (sensor_id,))
        
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


@app.delete("/api/sensors/{sensor_id}/delete")
async def delete_sensor(sensor_id: int, current_user: Dict = Depends(get_current_user)):
    """Delete a sensor (admin only or device owner)"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get sensor info
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
        
        sensor_name = sensor[1]
        device_uid = sensor[2]
        
        # Check access
        if not auth.user_can_access_device(current_user["user_id"], device_uid):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete sensor
        cur.execute("DELETE FROM sensors WHERE id = %s;", (sensor_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "message": f"Sensor '{sensor_name}' deleted successfully"
        }
        
    except HTTPException:
        if conn:
            conn.close()
        raise
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


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

@app.get("/sensors")
def sensors_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Sensors management page - redirects to login if not authenticated"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("sensors.html", {
        "request": request,
        "user": current_user
    })

