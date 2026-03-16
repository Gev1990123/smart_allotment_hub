from fastapi import APIRouter, Request, HTTPException, status, Cookie
from fastapi.responses import JSONResponse
from typing import Optional, Dict
from dependencies import get_current_user
from models import LoginRequest
from fastapi import Depends
import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
async def login(request: Request, login_data: LoginRequest):
    """Validate credentials and issue a session cookie"""
    user = auth.authenticate_user(login_data.username, login_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", None)

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

@router.post("/logout")
async def logout(session_token: Optional[str] = Cookie(None)):
    """Delete the server-side session and clear the cookie"""
    if session_token:
        auth.delete_session(session_token)

    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("session_token")

    return response

@router.get("/me")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Return basic info about the currently logged-in user"""
    return {
        "username": current_user["username"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": current_user["role"]
    }