"""
Authentication and Authorization utilities
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
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


# ============================================
# SESSION MANAGEMENT
# ============================================

def create_session(user_id: int, ip_address: str = None, user_agent: str = None) -> str:
    """
    Create a new session for a user
    Returns the session token
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
    Validate a session token
    Returns user info if valid, None if invalid/expired
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Clean up expired sessions first
    cur.execute("DELETE FROM sessions WHERE expires_at < NOW();")
    
    # Get session and user info
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
    """Delete a session (logout)"""
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
    Authenticate a user by username and password
    Returns user info if successful, None if failed
    """
    conn = get_connection()
    cur = conn.cursor()
    
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
    
    # Verify password
    if not verify_password(password, password_hash):
        conn.close()
        return None
    
    # Update last login
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
    Get list of site IDs a user has access to
    Returns empty list for sys_admin (they have access to all)
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
        return []  # Empty list means "all sites"
    
    # Get assigned sites for regular users
    cur.execute("""
        SELECT site_id FROM user_site_assignments WHERE user_id = %s;
    """, (user_id,))
    
    site_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    
    return site_ids


def user_can_access_site(user_id: int, site_id: int) -> bool:
    """Check if a user can access a specific site"""
    allowed_sites = get_user_site_access(user_id)
    
    # Empty list means sys_admin (access to all)
    if not allowed_sites:
        return True
    
    return site_id in allowed_sites


def user_can_access_device(user_id: int, device_uid: str) -> bool:
    """Check if a user can access a specific device"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get user's role and device's site_id
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
    
    # Device not assigned to a site - deny access for regular users
    if device_site_id is None:
        conn.close()
        return False
    
    # Check if user has access to this site
    cur.execute("""
        SELECT 1 FROM user_site_assignments
        WHERE user_id = %s AND site_id = %s;
    """, (user_id, device_site_id))
    
    has_access = cur.fetchone() is not None
    conn.close()
    
    return has_access


def filter_devices_by_access(user_id: int, devices: list) -> list:
    """
    Filter a list of devices based on user access
    Returns all devices for sys_admin, filtered list for regular users
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
    
    # Get user's allowed sites
    cur.execute("""
        SELECT site_id FROM user_site_assignments WHERE user_id = %s;
    """, (user_id,))
    
    allowed_sites = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Filter devices by site_id
    return [d for d in devices if d.get('site_id') in allowed_sites]