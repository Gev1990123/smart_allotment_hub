from fastapi import Cookie, Header, HTTPException, status
from typing import Optional, Dict, Any
import auth


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
    
    user_id = user.get("id") or user.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session: user missing id"
        )

    return {
        "id": user_id,
        **user  # keep other fields if needed
    }


async def get_optional_user(session_token: Optional[str] = Cookie(None)) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency — like get_current_user but returns None instead of
    raising an exception. Used on pages that redirect to /login if unauthenticated.
    """
    if not session_token:
        return None
    return auth.validate_session(session_token)


async def require_sys_admin(current_user: Dict = None) -> Dict[str, Any]:
    """
    FastAPI dependency — requires the logged-in user to have the sys_admin role.
    Raises 403 otherwise.
    """
    # Note: callers should chain this with Depends(get_current_user)
    # e.g. admin: Dict = Depends(require_sys_admin_dep)
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
    Used on endpoints accessible from both the browser UI and external API callers.
    """
    if session_token:
        user = auth.validate_session(session_token)
        if user:
            user["auth_type"] = "session"
            return user

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


# ------------------------------------------------------------------
# Reusable dependency that combines get_current_user + sys_admin check
# Import and use this directly with Depends() in routers
# ------------------------------------------------------------------
from fastapi import Depends


async def require_sys_admin_dep(current_user: Dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Convenience dependency: validates session AND enforces sys_admin role.
    Use as: admin: Dict = Depends(require_sys_admin_dep)
    """
    if current_user.get("role") != "sys_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user