"""
Authentication and Authorization utilities for Smart Allotment.
Covers password hashing, session management, API tokens, and access control.
"""
import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from db import get_connection

# ============================================
# PASSWORD HASHING
# ============================================

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt (includes a random salt automatically)"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

# ============================================
# API TOKEN MANAGEMENT
# ============================================

def generate_api_token(prefix: str = "api") -> str:
    """
    Generate a cryptographically secure API token.
    Format: {prefix}_{64-char hex string}
    Example: dev_a3f9bc... or usr_12cd8e...
    """
    random_part = secrets.token_hex(32)  # 64 character hex string
    return f"{prefix}_{random_part}"


def create_api_token(
    name: str,
    user_id: Optional[int] = None,
    device_id: Optional[int] = None,
    description: Optional[str] = None,
    scopes: Optional[list] = None,
    expires_days: Optional[int] = None,
    created_by: Optional[int] = None
) -> Dict[str, Any]:
    """
    Create and persist a new API token.
    Either user_id OR device_id must be provided (not both, not neither).
    Returns a dict including the raw token — this is the only time it's available in plaintext.
    """
    if not user_id and not device_id:
        raise ValueError("Either user_id or device_id must be provided")
    
    # Determine token prefix
    prefix = "dev" if device_id else "usr"
    token = generate_api_token(prefix)
    
    scopes = scopes or []

    # Calculate expiry if a lifespan was requested; None = never expires
    expires_at = None
    if expires_days:
        expires_at = datetime.now() + timedelta(days=expires_days)
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO api_tokens (token, user_id, device_id, name, description, scopes, expires_at, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, token, name, scopes, expires_at, created_at;
    """, (token, user_id, device_id, name, description, scopes, expires_at, created_by))
    
    row = cur.fetchone()
    conn.commit()
    conn.close()
    
    return {
        "id": row[0],
        "token": row[1], # Raw token — only returned here, never stored in plaintext
        "name": row[2],
        "scopes": row[3],
        "expires_at": row[4],
        "created_at": row[5]
    }


def validate_api_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate an API token from an Authorization header.
    Cleans up expired tokens as a side effect.
    Returns enriched token info (with user/device details) if valid, None if not.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Housekeeping: remove expired tokens before checking
    cur.execute("DELETE FROM api_tokens WHERE expires_at < NOW() AND expires_at IS NOT NULL;")
    
    # Fetch the token along with its associated user or device info
    cur.execute("""
        SELECT 
            t.id, t.token, t.user_id, t.device_id, t.name, t.scopes, t.expires_at,
            u.username, u.role, u.email,
            d.uid as device_uid, d.site_id
        FROM api_tokens t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN devices d ON t.device_id = d.id
        WHERE t.token = %s 
        AND t.active = TRUE
        AND (t.expires_at IS NULL OR t.expires_at > NOW());
    """, (token,))
    
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return None
    
    # Record when this token was last used (useful for auditing)
    cur.execute("""
        UPDATE api_tokens SET last_used = NOW() WHERE token = %s;
    """, (token,))
    
    conn.commit()
    conn.close()
    
    result = {
        "token_id": row[0],
        "token": row[1],
        "user_id": row[2],
        "device_id": row[3],
        "token_name": row[4],
        "scopes": row[5] or [],
        "expires_at": row[6],
        "type": "user" if row[2] else "device" # Tells callers which kind of token this is
    }
    
    # Attach user details if this is a user token
    if row[2]:
        result["username"] = row[7]
        result["role"] = row[8]
        result["email"] = row[9]
    
    # Attach device details if this is a device token
    if row[3]:
        result["device_uid"] = row[10]
        result["device_site_id"] = row[11]
    
    return result


def revoke_api_token(token: str) -> bool:
    """
    Soft-delete a token by marking it inactive.
    Returns True if a row was updated, False if the token wasn't found.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE api_tokens SET active = FALSE WHERE token = %s;
    """, (token,))
    
    affected = cur.rowcount
    conn.commit()
    conn.close()
    
    return affected > 0


def list_user_tokens(user_id: int) -> list:
    """Return all tokens belonging to a user, newest first. Token values are not included."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, name, scopes, active, last_used, expires_at, created_at
        FROM api_tokens
        WHERE user_id = %s
        ORDER BY created_at DESC;
    """, (user_id,))
    
    tokens = []
    for row in cur.fetchall():
        tokens.append({
            "id": row[0],
            "name": row[1],
            "scopes": row[2],
            "active": row[3],
            "last_used": row[4],
            "expires_at": row[5],
            "created_at": row[6]
        })
    
    conn.close()
    return tokens


def list_device_tokens(device_id: int) -> list:
    """Return all tokens associated with a device, newest first."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, name, scopes, active, last_used, expires_at, created_at
        FROM api_tokens
        WHERE device_id = %s
        ORDER BY created_at DESC;
    """, (device_id,))
    
    tokens = []
    for row in cur.fetchall():
        tokens.append({
            "id": row[0],
            "name": row[1],
            "scopes": row[2],
            "active": row[3],
            "last_used": row[4],
            "expires_at": row[5],
            "created_at": row[6]
        })
    
    conn.close()
    return tokens


def check_token_scope(token_info: Dict[str, Any], required_scope: str) -> bool:
    """
    Check whether a token has permission for a given scope.

    Scope format examples: 'read:sensors', 'write:sensor_data', 'admin:*'
    Matching rules (in order):
      1. 'admin:*'        → grants everything
      2. Exact match      → e.g. 'write:sensor_data' matches 'write:sensor_data'
      3. Wildcard prefix  → e.g. 'read:*' matches 'read:sensors'
    """
    scopes = token_info.get("scopes", [])
    
    # Admin wildcard
    if "admin:*" in scopes:
        return True
    
    # Exact match
    if required_scope in scopes:
        return True
    
    # Check if a wildcard like 'read:*' covers the required scope
    scope_parts = required_scope.split(":")
    if len(scope_parts) == 2:
        wildcard = f"{scope_parts[0]}:*"
        if wildcard in scopes:
            return True
    
    return False

# ============================================
# SESSION MANAGEMENT
# ============================================

def create_session(user_id: int, ip_address: str = None, user_agent: str = None) -> str:
    """
    Create a new browser session for a user after successful login.
    Sessions expire after 24 hours.
    Returns the session token (stored as an httponly cookie on the client).
    """
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=24)  # 24 hour sessions
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO sessions (user_id, session_token, expires_at, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING session_token;
    """, (user_id, session_token, expires_at, ip_address, user_agent))
    
    token = cur.fetchone()[0]
    conn.commit()
    conn.close()
    
    return token


def validate_session(session_token: str) -> Optional[Dict[str, Any]]:
    """
    Validate a session cookie token.
    Cleans up expired sessions as a side effect.
    Returns user info dict if valid, None if expired or not found.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Housekeeping: purge expired sessions before checking
    cur.execute("DELETE FROM sessions WHERE expires_at < NOW();")
    
    # Join to users so we get role/email etc. in a single query
    cur.execute("""
        SELECT 
            u.id, u.username, u.email, u.full_name, u.role, u.active,
            s.expires_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_token = %s AND s.expires_at > NOW() AND u.active = TRUE;
    """, (session_token,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "user_id": row[0],
        "username": row[1],
        "email": row[2],
        "full_name": row[3],
        "role": row[4],
        "active": row[5],
        "session_expires": row[6]
    }


def delete_session(session_token: str):
    """Remove a session from the DB (called on logout)"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM sessions WHERE session_token = %s;", (session_token,))
    
    conn.commit()
    conn.close()


# ============================================
# USER AUTHENTICATION
# ============================================

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verify a username/password pair.
    Returns user info on success, None on failure (wrong credentials or inactive account).
    Also updates last_login timestamp on success.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Only fetch active users — deactivated accounts are treated as non-existent
    cur.execute("""
        SELECT id, username, email, password_hash, full_name, role, active
        FROM users
        WHERE username = %s AND active = TRUE;
    """, (username,))
    
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return None
    
    user_id, username, email, password_hash, full_name, role, active = row
    
    # bcrypt comparison — timing-safe
    if not verify_password(password, password_hash):
        conn.close()
        return None
    
    # Track when the user last logged in
    cur.execute("""
        UPDATE users SET last_login = NOW() WHERE id = %s;
    """, (user_id,))
    
    conn.commit()
    conn.close()
    
    return {
        "user_id": user_id,
        "username": username,
        "email": email,
        "full_name": full_name,
        "role": role
    }


# ============================================
# AUTHORIZATION
# ============================================

def get_user_site_access(user_id: int) -> list[int]:
    """
    Return the list of site IDs a user is allowed to access.
    For sys_admin users, returns an empty list — callers treat empty as "all sites".
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if user is sys_admin
    cur.execute("SELECT role FROM users WHERE id = %s;", (user_id,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return []
    
    role = row[0]
    
    if role == 'sys_admin':
        conn.close()
        return []  # Convention: empty = unrestricted (sys_admin sees everything)
    
    # For regular users, return only their explicitly assigned sites
    cur.execute("""
        SELECT site_id FROM user_site_assignments WHERE user_id = %s;
    """, (user_id,))
    
    site_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    
    return site_ids


def user_can_access_site(user_id: int, site_id: int) -> bool:
    """Return True if the user has access to the given site"""
    allowed_sites = get_user_site_access(user_id)
    
    # Empty list = sys_admin = access to all sites
    if not allowed_sites:
        return True
    
    return site_id in allowed_sites


def user_can_access_device(user_id: int, device_uid: str) -> bool:
    """
    Return True if the user has access to the given device.
    Access is determined by whether the user has access to the site the device belongs to.
    Devices with no site assigned are only accessible by sys_admin.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Fetch role and device site_id in a single CROSS JOIN query
    cur.execute("""
        SELECT u.role, d.site_id
        FROM users u
        CROSS JOIN devices d
        WHERE u.id = %s AND d.uid = %s;
    """, (user_id, device_uid))
    
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return False
    
    role, device_site_id = row
    
    # sys_admin can access everything
    if role == 'sys_admin':
        conn.close()
        return True
    
    # Unassigned devices are off-limits to regular users
    if device_site_id is None:
        conn.close()
        return False
    
    # Check the user_site_assignments table
    cur.execute("""
        SELECT 1 FROM user_site_assignments
        WHERE user_id = %s AND site_id = %s;
    """, (user_id, device_site_id))
    
    has_access = cur.fetchone() is not None
    conn.close()
    
    return has_access

def token_can_access_device(token_info: Dict[str, Any], device_uid: str) -> bool:
    """
    Check device access for an API token.
    - Device tokens: can only access their own device
    - User tokens: follow the same rules as user_can_access_device
    """

    if token_info["type"] == "device":
        # A device token is scoped to exactly one device
        return token_info.get("device_uid") == device_uid
    
    # User tokens follow user permissions
    if token_info["type"] == "user":
        user_id = token_info["user_id"]
        return user_can_access_device(user_id, device_uid)
    
    return False

def filter_devices_by_access(user_id: int, devices: list) -> list:
    """
    Filter a list of device dicts to only those the user can access.
    sys_admin receives the full unfiltered list.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if user is sys_admin
    cur.execute("SELECT role FROM users WHERE id = %s;", (user_id,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return []
    
    role = row[0]
    
    if role == 'sys_admin':
        conn.close()
        return devices  # Return all devices
    
    # Get the user's allowed site IDs
    cur.execute("""
        SELECT site_id FROM user_site_assignments WHERE user_id = %s;
    """, (user_id,))
    
    allowed_sites = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Keep only devices whose site_id is in the allowed list
    return [d for d in devices if d.get('site_id') in allowed_sites]