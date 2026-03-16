from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict
from dependencies import require_sys_admin_dep
from models import UserCreate, UserUpdate
from db import get_connection
import auth

router = APIRouter(prefix="/api/users", tags=["users"])

@router.post("/create")
async def create_user(user_data: UserCreate, admin: Dict = Depends(require_sys_admin_dep)):
    """Create a new user — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT username FROM users WHERE username = %s OR email = %s;
    """, (user_data.username, user_data.email))

    if cur.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )

    password_hash = auth.hash_password(user_data.password)

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

@router.post("/{user_id}/assign-site/{site_id}")
async def assign_user_to_site(user_id: int, site_id: int, admin: Dict = Depends(require_sys_admin_dep)):
    """Grant a user access to a site — sys_admin only"""
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

@router.delete("/{user_id}/unassign-site/{site_id}")
async def unassign_user_from_site(user_id: int, site_id: int, admin: Dict = Depends(require_sys_admin_dep)):
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

@router.get("/list")
async def list_users(admin: Dict = Depends(require_sys_admin_dep)):
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

@router.put("/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, admin: Dict = Depends(require_sys_admin_dep)):
    """Update a user's details — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE id = %s;", (user_id,))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        cur.execute(
            "SELECT id FROM users WHERE email = %s AND id != %s;",
            (user_data.email, user_id)
        )
        if cur.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already in use by another user")

        if user_data.password:
            password_hash = auth.hash_password(user_data.password)
            cur.execute("""
                UPDATE users
                SET email = %s, full_name = %s, role = %s, password_hash = %s
                WHERE id = %s
                RETURNING id, username, email, full_name, role;
            """, (user_data.email, user_data.full_name, user_data.role, password_hash, user_id))
        else:
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

@router.delete("/{user_id}")
async def delete_user(user_id: int, admin: Dict = Depends(require_sys_admin_dep)):
    """Delete a user and all their site assignments — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if user_id == admin["user_id"]:
            conn.close()
            raise HTTPException(status_code=400, detail="You cannot delete your own account")

        cur.execute("SELECT username FROM users WHERE id = %s;", (user_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        username = row[0]

        cur.execute("DELETE FROM user_site_assignments WHERE user_id = %s;", (user_id,))
        cur.execute("DELETE FROM sessions WHERE user_id = %s;", (user_id,))
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

@router.get("/{user_id}/sites")
async def get_user_sites(user_id: int, admin: Dict = Depends(require_sys_admin_dep)):
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