from fastapi import FastAPI, Request, Depends, HTTPException, status, Cookie, Header
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from pydantic import BaseModel
from db import get_connection
import auth
import mqtt_publisher

app = FastAPI(title="Smart Allotment API")

# Allow all origins for now — tighten this down in production
# to only allow the frontend's actual domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS) and HTML templates from fixed container paths
app.mount("/static", StaticFiles(directory="/api/static"), name="static")
templates = Jinja2Templates(directory="/api/templates")

# -------------------------
# Startup
# -------------------------

@app.on_event("startup")
async def startup():
    # Connect the persistent MQTT publisher once when the API boots,
    # so all endpoints can publish without creating a new connection each time
    mqtt_publisher.connect()

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

class UserUpdate(BaseModel):
    email: str
    full_name: str | None = None
    role: str = "user"
    password: str | None = None # Optional — only update if provided

class ApiTokenCreate(BaseModel):
    name: str
    description: str | None = None
    scopes: list[str] = []
    expires_days: int | None = None
    device_uid: str | None = None  # If set, creates a device token instead of a user token

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

class PumpCommand(BaseModel):
    action: str  # "on" or "off"
    seconds: int | None = None    # Required when action == "run"

# -------------------------
# Authentication Dependency
# -------------------------

async def get_current_user(session_token: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    """
    FastAPI dependency — extracts and validates the session cookie.
    Raises 401 if the cookie is missing or the session has expired.
    """
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
    """
    FastAPI dependency — like get_current_user but returns None instead of
    raising an exception. Used on pages that redirect to /login if unauthenticated.
    """
    if not session_token:
        return None
    return auth.validate_session(session_token)

async def require_sys_admin(current_user: Dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    FastAPI dependency — requires the logged-in user to have the sys_admin role.
    Raises 403 otherwise.
    """
    if current_user.get("role") != "sys_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def get_api_token_auth(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency — authenticates via Bearer token in the Authorization header.
    Used by IoT devices and external API callers.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Strip the "Bearer " prefix if present
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
    FastAPI dependency — accepts either a session cookie OR a Bearer API token.
    Session cookie is checked first; API token is the fallback.
    Used on endpoints that should be accessible from both the browser UI
    and external API callers (e.g. the node's HTTP calls).
    """
    # Try session cookie first (browser users)
    if session_token:
        user = auth.validate_session(session_token)
        if user:
            user["auth_type"] = "session"
            return user
    
    # Fall back to API token (devices / external callers)
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
    """Validate credentials and issue a session cookie"""
    user = auth.authenticate_user(login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Capture client metadata for the session record
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
    
    # httponly prevents JS from reading the cookie (XSS protection)
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
    """Delete the server-side session and clear the cookie"""
    if session_token:
        auth.delete_session(session_token)
    
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("session_token")
    
    return response

@app.get("/api/auth/me")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Return basic info about the currently logged-in user"""
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
    """Create a new user — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Prevent duplicate usernames or email addresses
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
    """Grant a user access to a site — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # ON CONFLICT DO NOTHING = idempotent; assigning twice won't error
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
    """Revoke a user's access to a site — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM user_site_assignments
        WHERE user_id = %s AND site_id = %s;
    """, (user_id, site_id))
    
    conn.commit()
    conn.close()
    
    return {"message": f"User {user_id} unassigned from site {site_id}"}

@app.get("/api/users/list")
async def list_users(admin: Dict = Depends(require_sys_admin)):
    """List all users — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, username, email, full_name, role, created_at
            FROM users
            ORDER BY id;
        """)
        rows = cur.fetchall()
        conn.close()
        return {
            "users": [
                {
                    "id": r[0],
                    "username": r[1],
                    "email": r[2],
                    "full_name": r[3],
                    "role": r[4],
                    "created_at": r[5].isoformat() if r[5] else None
                }
                for r in rows
            ]
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, admin: Dict = Depends(require_sys_admin)):
    """Update a user's details — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check user exists
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        # Ensure the new email isn't already taken by a different user
        cur.execute(
            "SELECT id FROM users WHERE email = %s AND id != %s;",
            (user_data.email, user_id)
        )
        if cur.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already in use by another user")

        if user_data.password:
            # Password change requested — re-hash and update together
            password_hash = auth.hash_password(user_data.password)
            cur.execute("""
                UPDATE users
                SET email = %s, full_name = %s, role = %s, password_hash = %s
                WHERE id = %s
                RETURNING id, username, email, full_name, role;
            """, (user_data.email, user_data.full_name, user_data.role, password_hash, user_id))
        else:
            # No password change — leave password_hash untouched
            cur.execute("""
                UPDATE users
                SET email = %s, full_name = %s, role = %s
                WHERE id = %s
                RETURNING id, username, email, full_name, role;
            """, (user_data.email, user_data.full_name, user_data.role, user_id))

        updated = cur.fetchone()
        conn.commit()
        conn.close()
        return {
            "user_id": updated[0],
            "username": updated[1],
            "email": updated[2],
            "full_name": updated[3],
            "role": updated[4]
        }
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, admin: Dict = Depends(require_sys_admin)):
    """Delete a user and all their site assignments — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Safety check: prevent an admin from deleting their own account
        if user_id == admin["user_id"]:
            conn.close()
            raise HTTPException(status_code=400, detail="You cannot delete your own account")

        cur.execute("SELECT username FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        username = row[0]

        # Clean up related records before deleting the user row
        cur.execute("DELETE FROM user_site_assignments WHERE user_id = %s;", (user_id,))
        # Remove sessions
        cur.execute("DELETE FROM sessions WHERE user_id = %s;", (user_id,))
        # Remove the user
        cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))

        conn.commit()
        conn.close()
        return {"message": f"User '{username}' deleted successfully"}
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}/sites")
async def get_user_sites(user_id: int, admin: Dict = Depends(require_sys_admin)):
    """Get all sites assigned to a specific user — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT s.id, s.site_code, s.friendly_name
            FROM sites s
            JOIN user_site_assignments usa ON s.id = usa.site_id
            WHERE usa.user_id = %s
            ORDER BY s.site_code;
        """, (user_id,))
        rows = cur.fetchall()
        conn.close()
        return {
            "sites": [
                {"id": r[0], "site_code": r[1], "friendly_name": r[2]}
                for r in rows
            ]
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# API TOKEN MANAGEMENT
# ---------------------------------------------------------

@app.post("/api/tokens/create")
async def create_token(token_data: ApiTokenCreate, current_user: Dict = Depends(get_current_user)):
    """
    Create a new API token.
    - If device_uid is provided → device token (admin only)
    - Otherwise → user token for the currently logged-in user
    """
    
    user_id = None
    device_id = None
    
    if token_data.device_uid:
        # Device tokens can only be created by admins
        if current_user.get("role") != "sys_admin":
            raise HTTPException(status_code=403, detail="Only admins can create device tokens")
        
        # Resolve device UID to internal device ID
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE uid = %s;", (token_data.device_uid,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        device_id = row[0]
    else:
        # User token — associate with the caller's own account
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
            "token": token["token"],  # Shown only once — user must save it now
            "id": token["id"],
            "name": token["name"],
            "scopes": token["scopes"],
            "expires_at": token["expires_at"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tokens/list")
async def list_my_tokens(current_user: Dict = Depends(get_current_user)):
    """List the current user's API tokens (metadata only — no token values)"""
    tokens = auth.list_user_tokens(current_user["user_id"])
    
    # Don't return actual token values, just metadata
    return {"tokens": tokens}


@app.delete("/api/tokens/{token_id}/revoke")
async def revoke_token(token_id: int, current_user: Dict = Depends(get_current_user)):
    """Revoke (deactivate) a token — owner or sys_admin only"""
    
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
    
    # Only the token's owner or an admin can revoke it
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
    """
    Submit sensor data — device API token only.
    The device is identified by the token itself (not the request body),
    so a token can only ever write data for its own device.
    """
    
    # Reject user tokens — only physical devices should submit data this way
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
        
        # Mark device as active and record the timestamp of this reading
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
    """Simple liveness check — also verifies the DB connection is reachable"""
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
    """
    Return the most recent reading for each sensor type on a device.
    DISTINCT ON (sensor_type) gives us one row per type, ordered by most recent.
    """

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
    """
    Return all readings for a device within the last N hours (default 24).
    Results are ordered oldest-first so charts render left-to-right chronologically.
    """
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
            ORDER BY time_bucket ASC;""", 
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
                "sensor_type": row[1],
                "unit": row[4]
            })
        
        return rows

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------
# LIST ALL UNIQUE DEVICES (filtered by user access)
# ---------------------------------------------------------
@app.get("/api/devices")
def list_devices(current_user: Dict = Depends(get_auth_user_or_token)):
    """
    List devices the current user can access.
    sys_admin sees all; regular users only see devices on their assigned sites.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Get user's allowed sites
        allowed_sites = auth.get_user_site_access(current_user["user_id"])

        if not allowed_sites:
            # Empty list = sys_admin — fetch everything
            cur.execute("SELECT DISTINCT uid, name, site_id FROM devices WHERE uid IS NOT NULL ORDER BY uid;")
        else:
            # Build a dynamic IN clause for the user's allowed site IDs
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
    """Return all registered sites (unfiltered — used for dropdowns etc.)"""
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
    """Return all unique sensor IDs (legacy endpoint — used for dropdowns)"""
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
    """Register a new device — sys_admin only. Device starts inactive until it sends data."""
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
    """Register a new site — sys_admin only"""
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
    """List sensors — sys_admin sees all, regular users see only their sites' sensors"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get user's allowed sites
        allowed_sites = auth.get_user_site_access(current_user["user_id"])
        
        if not allowed_sites:
            # sys_admin — no site filter
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
    """Register a new sensor against a device the user has access to"""
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
        
        # Prevent duplicate sensor names on the same device
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
        
        # Auto-assign a sensible unit if none was provided
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
    """Mark a sensor as active so it appears in dashboards"""
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Join to devices so we can check access via device_uid
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
    """Mark a sensor as inactive (hides it from dashboards without deleting data)"""
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
    """Permanently delete a sensor record — does NOT delete historical sensor_data rows"""
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
# MANUAL READ-NOW
# ---------------------------------------------------------

@app.post("/api/devices/{device_uid}/read-now")
async def trigger_manual_reading(device_uid: str, current_user: Dict = Depends(get_auth_user_or_token)):
    """
    Send an MQTT command to trigger an immediate sensor reading on the device.
    The node publishes the result to sensors/{uid}/data which the listener picks up normally.
    """
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

# ---------------------------------------------------------
# MANUAL PUMP-NOW
# ---------------------------------------------------------

@app.post("/api/devices/{device_uid}/pump")
async def trigger_pump(device_uid: str, command: PumpCommand, current_user: Dict = Depends(get_auth_user_or_token)):
    """
    Send an MQTT pump command to a device — sys_admin only.
    Actions: 'on' (stay on), 'off' (turn off), 'run' (on for N seconds then auto-off).
    """
    if current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(status_code=403, detail="Access denied")

    if command.action not in ("on", "off", "run"):
        raise HTTPException(status_code=400, detail="Action must be 'on', 'off', or 'run'")

    # 'run' needs a duration so the node knows when to stop
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

@app.get("/users")
def users_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    """Users management page — admin only"""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return templates.TemplateResponse("users.html", {
        "request": request,
        "user": current_user
    })

