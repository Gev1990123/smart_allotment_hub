from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from dependencies import get_auth_user_or_token
import auth

router = APIRouter(prefix="/api", tags=["predictions"])


@router.get("/predictions/{device_uid}")
async def device_predictions(
    device_uid: str,
    lat: float = 51.7731,
    lon: float = 0.6149,
    planting_date: str | None = None,
    current_user: Dict = Depends(get_auth_user_or_token),
):
    """
    Return watering recommendations, frost alerts, and growth forecast
    for a device.

    Query params:
      lat           — latitude of the allotment (defaults to config value)
      lon           — longitude of the allotment (defaults to config value)
      planting_date — optional ISO date string (YYYY-MM-DD) for GDD tracking
    """
    if not auth.user_can_access_device(current_user["user_id"], device_uid):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        from predictions import get_predictions
        result = await get_predictions(
            device_uid=device_uid,
            lat=lat,
            lon=lon,
            planting_date=planting_date,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weather")
async def weather_forecast(
    lat: float = 51.7731,
    lon: float = 0.6149,
    current_user: Dict = Depends(get_auth_user_or_token),
):
    """
    Return raw 7-day Open-Meteo forecast for the given coordinates.
    Useful for dashboard weather widgets independent of a specific device.
    """
    try:
        from predictions import fetch_weather_forecast
        data = await fetch_weather_forecast(lat, lon)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather API error: {e}")