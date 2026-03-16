from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, Dict
from dependencies import get_optional_user
import auth

router = APIRouter(tags=["ui"])

# Templates are configured here but the directory must match what app.py sets up.
# If you ever move the templates directory, update both this file and app.py.
templates = Jinja2Templates(directory="/api/templates")

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/")
def dashboard(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

@router.get("/devices")
def devices_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("devices.html", {"request": request, "user": current_user})

@router.get("/sites")
def sites_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("sites.html", {"request": request, "user": current_user})

@router.get("/device/{device_id}")
def device_page(device_id: str, request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if not auth.user_can_access_device(current_user["user_id"], device_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return templates.TemplateResponse(
        "device.html",
        {"request": request, "device_id": device_id, "user": current_user}
    )

@router.get("/site/{site_id}")
def site_page(site_id: int, request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if not auth.user_can_access_site(current_user["user_id"], site_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return templates.TemplateResponse(
        "site.html",
        {"request": request, "site_id": site_id, "user": current_user}
    )

@router.get("/sensors")
def sensors_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("sensors.html", {"request": request, "user": current_user})

@router.get("/users")
def users_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if current_user.get("role") != "sys_admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return templates.TemplateResponse("users.html", {"request": request, "user": current_user})

@router.get("/plant-profiles")
def plant_profiles_page(request: Request, current_user: Optional[Dict] = Depends(get_optional_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("plant_profiles.html", {"request": request, "user": current_user})

@router.get("/predictions/{device_id}")
def predictions_page(
    device_id: str,
    request: Request,
    current_user: Optional[Dict] = Depends(get_optional_user),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if not auth.user_can_access_device(current_user["user_id"], device_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return templates.TemplateResponse(
        "predictions.html",
        {"request": request, "device_id": device_id, "user": current_user},
    )