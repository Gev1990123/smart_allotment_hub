from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict
from dependencies import get_current_user
from models import ApiTokenCreate
from db import get_connection
import auth

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

@router.post("/create")
async def create_token(token_data: ApiTokenCreate, current_user: Dict = Depends(get_current_user)):
    """
    Create a new API token.
    - If device_uid is provided → device token (admin only)
    - Otherwise → user token for the currently logged-in user
    """
    user_id = None
    device_id = None

    if token_data.device_uid:
        if current_user.get("role") != "sys_admin":
            raise HTTPException(status_code=403, detail="Only admins can create device tokens")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE uid = %s;", (token_data.device_uid,))
        row = cur.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        device_id = row[0]
    else:
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

@router.get("/list")
async def list_my_tokens(current_user: Dict = Depends(get_current_user)):
    """List the current user's API tokens (metadata only — no token values)"""
    tokens = auth.list_user_tokens(current_user["user_id"])
    return {"tokens": tokens}

@router.delete("/{token_id}/revoke")
async def revoke_token(token_id: int, current_user: Dict = Depends(get_current_user)):
    """Revoke (deactivate) a token — owner or sys_admin only"""
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

    if token_user_id != current_user["user_id"] and current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Not authorized to revoke this token")

    success = auth.revoke_api_token(token_value)

    if success:
        return {"message": "Token revoked successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to revoke token")