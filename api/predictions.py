"""
predictions.py — Smart Allotment Prediction Engine
====================================================
Combines historical sensor data (soil moisture, temperature, light)
from your TimescaleDB with Open-Meteo weather forecasts to produce:
"""

import httpx
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from db import get_connection

logger = logging.getLogger("predictions")

# ---------------------------------------------------------------------------
# Open-Meteo config
# ---------------------------------------------------------------------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_LAT = 51.7731
DEFAULT_LON = 0.6149

# ---------------------------------------------------------------------------
# Thresholds (tune these to your plants / soil type)
# ---------------------------------------------------------------------------
MOISTURE_WATER_THRESHOLD   = 35.0   # % — below this → water needed
MOISTURE_SKIP_THRESHOLD    = 65.0   # % — above this → definitely skip watering
FROST_TEMP_THRESHOLD       = 2.0    # °C — warn when forecast dips below this
HEAVY_RAIN_MM_THRESHOLD    = 10.0   # mm/day — skip watering if heavy rain forecast
BASE_TEMP_GDD              = 10.0   # °C base for Growing Degree Days calculation


# ===========================================================================
# WEATHER FETCHER
# ===========================================================================

async def fetch_weather_forecast(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> dict:
    """
    Fetch 7-day hourly forecast from Open-Meteo.
    Returns raw JSON or raises on network failure.
    """
    params = {
        "latitude":  lat,
        "longitude": lon,
        "hourly": [
            "temperature_2m",
            "precipitation",
            "precipitation_probability",
            "weathercode",
            "uv_index",
            "windspeed_10m",
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "weathercode",
            "uv_index_max",
            "sunrise",
            "sunset",
        ],
        "timezone":        "auto",
        "forecast_days":   7,
        "wind_speed_unit": "ms",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        return resp.json()


# ===========================================================================
# SENSOR DATA HELPERS
# ===========================================================================

def get_recent_sensor_avg(device_uid: str, sensor_type: str, hours: int = 6) -> Optional[float]:
    """
    Return the average sensor value for a device over the last N hours.
    Returns None if no data is found.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT AVG(sd.value)
            FROM sensor_data sd
            JOIN devices d ON d.id = sd.device_id
            WHERE d.uid = %s
              AND sd.sensor_type = %s
              AND sd.time > NOW() - INTERVAL '%s hours'
        """, (device_uid, sensor_type, hours))
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()


def get_sensor_trend(device_uid: str, sensor_type: str, hours: int = 24) -> Optional[str]:
    """
    Compare the last 3-hour average to the previous period and return
    'rising', 'falling', or 'stable'.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                AVG(CASE WHEN sd.time > NOW() - INTERVAL '3 hours' THEN sd.value END) AS recent,
                AVG(CASE WHEN sd.time <= NOW() - INTERVAL '3 hours'
                         AND sd.time > NOW() - INTERVAL '%s hours'
                    THEN sd.value END) AS older
            FROM sensor_data sd
            JOIN devices d ON d.id = sd.device_id
            WHERE d.uid = %s AND sd.sensor_type = %s
        """, (hours, device_uid, sensor_type))
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        diff = float(row[0]) - float(row[1])
        if diff > 2:
            return "rising"
        if diff < -2:
            return "falling"
        return "stable"
    finally:
        conn.close()


def get_last_pump_event(device_uid: str) -> Optional[datetime]:
    """Return the timestamp of the most recent pump 'on' event for a device."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT pe.event_time
            FROM pump_events pe
            JOIN sites s ON s.id = pe.site_id
            JOIN devices d ON d.site_id = s.id
            WHERE d.uid = %s AND pe.action = 'on'
            ORDER BY pe.event_time DESC
            LIMIT 1
        """, (device_uid,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ===========================================================================
# PREDICTION ENGINES
# ===========================================================================

def predict_watering(
    moisture_pct: Optional[float],
    moisture_trend: Optional[str],
    daily_forecast: list,
    last_pump: Optional[datetime],
) -> dict:
    """
    Decide whether and when to water.

    Logic:
      - Skip if moisture is already high
      - Skip if heavy rain forecast in next 24 h
      - Recommend watering if moisture is low AND rain not expected
      - Factor in moisture trend (falling = water sooner)
    """
    reasons = []
    recommendation = "no_action"
    urgency = "low"
    suggested_in_hours = None

    # --- Rain check (next 24 h = first daily entry) ---
    rain_tomorrow = daily_forecast[0]["precipitation_sum"] if daily_forecast else 0
    rain_prob     = daily_forecast[0]["precipitation_probability_max"] if daily_forecast else 0
    heavy_rain_coming = (
        rain_tomorrow >= HEAVY_RAIN_MM_THRESHOLD and rain_prob >= 60
    )

    # --- Moisture checks ---
    if moisture_pct is None:
        reasons.append("No recent moisture data — cannot make a confident recommendation.")
        recommendation = "check_sensors"
    elif moisture_pct >= MOISTURE_SKIP_THRESHOLD:
        reasons.append(f"Soil moisture is {moisture_pct:.1f}% — well hydrated, no watering needed.")
        recommendation = "no_action"
    elif moisture_pct < MOISTURE_WATER_THRESHOLD:
        if heavy_rain_coming:
            reasons.append(
                f"Moisture is low ({moisture_pct:.1f}%) but {rain_tomorrow:.1f} mm rain "
                f"is forecast tomorrow ({rain_prob}% probability) — consider waiting."
            )
            recommendation = "wait_for_rain"
            suggested_in_hours = 24
        else:
            if moisture_trend == "falling":
                urgency = "high"
                suggested_in_hours = 2
                reasons.append(
                    f"Moisture is {moisture_pct:.1f}% and falling — water soon."
                )
            else:
                urgency = "medium"
                suggested_in_hours = 6
                reasons.append(
                    f"Moisture is {moisture_pct:.1f}% — below threshold, water today."
                )
            recommendation = "water_now"
    else:
        # Between thresholds — borderline
        if moisture_trend == "falling":
            reasons.append(
                f"Moisture is {moisture_pct:.1f}% and trending down — monitor and water if it drops further."
            )
            recommendation = "monitor"
            urgency = "low"
            suggested_in_hours = 12
        else:
            reasons.append(f"Moisture is {moisture_pct:.1f}% — acceptable, no action yet.")
            recommendation = "no_action"

    # --- Last pump context ---
    if last_pump:
        hours_since = (datetime.now(timezone.utc) - last_pump).total_seconds() / 3600
        reasons.append(f"Last watering was {hours_since:.0f} hours ago.")

    return {
        "recommendation": recommendation,   # water_now | wait_for_rain | monitor | no_action | check_sensors
        "urgency":        urgency,           # high | medium | low
        "reasons":        reasons,
        "suggested_in_hours": suggested_in_hours,
        "moisture_pct":   moisture_pct,
        "moisture_trend": moisture_trend,
        "rain_forecast_mm": rain_tomorrow,
        "rain_probability": rain_prob,
    }


def predict_frost_alerts(hourly_forecast: list, daily_forecast: list) -> dict:
    """
    Scan the 7-day forecast for frost risk (temp ≤ FROST_TEMP_THRESHOLD)
    and return alert details.
    """
    alerts = []
    frost_nights = []

    for day in daily_forecast:
        if day["temperature_2m_min"] is not None and day["temperature_2m_min"] <= FROST_TEMP_THRESHOLD:
            frost_nights.append({
                "date":    day["date"],
                "min_temp": round(day["temperature_2m_min"], 1),
                "severity": "hard_frost" if day["temperature_2m_min"] <= -2 else "light_frost",
            })

    if frost_nights:
        next_frost = frost_nights[0]
        severity_label = "Hard frost" if next_frost["severity"] == "hard_frost" else "Light frost"
        alerts.append({
            "type":    "frost",
            "title":   f"{severity_label} risk on {next_frost['date']}",
            "detail":  f"Forecast low of {next_frost['min_temp']}°C. "
                       f"Protect tender plants — cover with fleece tonight.",
            "date":    next_frost["date"],
            "min_temp": next_frost["min_temp"],
        })

    # Heavy rain alert
    for day in daily_forecast[:3]:
        if (day["precipitation_sum"] or 0) >= HEAVY_RAIN_MM_THRESHOLD:
            alerts.append({
                "type":   "heavy_rain",
                "title":  f"Heavy rain forecast on {day['date']}",
                "detail": f"{day['precipitation_sum']:.1f} mm expected — skip watering that day.",
                "date":   day["date"],
                "rain_mm": day["precipitation_sum"],
            })
            break

    return {
        "alerts":      alerts,
        "frost_nights": frost_nights,
        "alert_count": len(alerts),
    }


def predict_growth(
    device_uid: str,
    daily_forecast: list,
    light_lux: Optional[float],
    planting_date: Optional[str] = None,
) -> dict:
    """
    Estimate plant growth using Growing Degree Days (GDD).

    GDD = max(0, (T_max + T_min) / 2 - BASE_TEMP)

    Higher GDD → faster growth. Light level is used to flag
    whether photosynthesis conditions are favourable.
    """
    # Historical GDD from DB (last 30 days)
    conn = get_connection()
    cur = conn.cursor()
    historical_gdd = 0.0
    try:
        cur.execute("""
            SELECT
                date_trunc('day', sd.time) AS day,
                MAX(sd.value) AS t_max,
                MIN(sd.value) AS t_min
            FROM sensor_data sd
            JOIN devices d ON d.id = sd.device_id
            WHERE d.uid = %s
              AND sd.sensor_type = 'temperature'
              AND sd.time > NOW() - INTERVAL '30 days'
            GROUP BY date_trunc('day', sd.time)
        """, (device_uid,))
        rows = cur.fetchall()
        for row in rows:
            t_max, t_min = float(row[1]), float(row[2])
            gdd = max(0.0, ((t_max + t_min) / 2) - BASE_TEMP_GDD)
            historical_gdd += gdd
    finally:
        conn.close()

    # Forecast GDD (next 7 days)
    forecast_gdd = 0.0
    daily_gdd_forecast = []
    for day in daily_forecast:
        t_max = day.get("temperature_2m_max") or 0
        t_min = day.get("temperature_2m_min") or 0
        gdd = max(0.0, ((t_max + t_min) / 2) - BASE_TEMP_GDD)
        forecast_gdd += gdd
        daily_gdd_forecast.append({
            "date": day["date"],
            "gdd":  round(gdd, 1),
            "t_max": round(t_max, 1),
            "t_min": round(t_min, 1),
        })

    total_gdd = historical_gdd + forecast_gdd

    # Simple growth stage mapping (generic vegetables — tune per crop)
    if total_gdd < 50:
        stage = "germination"
        stage_label = "🌱 Germination / Seedling"
        stage_tip = "Keep soil consistently moist. Protect from cold."
    elif total_gdd < 150:
        stage = "early_growth"
        stage_label = "🌿 Early Vegetative Growth"
        stage_tip = "Plants establishing. Begin regular feeding."
    elif total_gdd < 300:
        stage = "vegetative"
        stage_label = "🥬 Active Vegetative Growth"
        stage_tip = "Peak growth period. Ensure adequate water and nutrients."
    elif total_gdd < 500:
        stage = "flowering"
        stage_label = "🌸 Flowering / Fruiting"
        stage_tip = "Reduce nitrogen, increase potassium. Keep pollinator-friendly."
    else:
        stage = "maturity"
        stage_label = "🍅 Approaching Maturity"
        stage_tip = "Begin harvest checks. Reduce watering slightly."

    # Light assessment
    light_assessment = None
    if light_lux is not None:
        if light_lux < 1000:
            light_assessment = "Low light — consider repositioning plants or supplementing."
        elif light_lux < 10000:
            light_assessment = "Moderate light — adequate for most vegetables."
        else:
            light_assessment = "Good light conditions — optimal for growth."

    return {
        "historical_gdd":     round(historical_gdd, 1),
        "forecast_gdd_7d":    round(forecast_gdd, 1),
        "total_gdd":          round(total_gdd, 1),
        "growth_stage":       stage,
        "growth_stage_label": stage_label,
        "growth_stage_tip":   stage_tip,
        "daily_gdd_forecast": daily_gdd_forecast,
        "light_lux":          light_lux,
        "light_assessment":   light_assessment,
        "planting_date":      planting_date,
    }


# ===========================================================================
# TOP-LEVEL PREDICTION AGGREGATOR
# ===========================================================================

async def get_predictions(
    device_uid: str,
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    planting_date: Optional[str] = None,
) -> dict:
    """
    Run all prediction engines and return a combined payload.
    Called by the FastAPI endpoint.
    """
    # --- Fetch sensor averages ---
    moisture_pct   = get_recent_sensor_avg(device_uid, "moisture",     hours=6)
    temperature    = get_recent_sensor_avg(device_uid, "temperature",  hours=1)
    light_lux      = get_recent_sensor_avg(device_uid, "light",        hours=1)
    moisture_trend = get_sensor_trend(device_uid, "moisture")
    last_pump      = get_last_pump_event(device_uid)

    # --- Fetch weather ---
    weather = await fetch_weather_forecast(lat, lon)

    # Parse daily forecast into a friendlier list
    daily_keys = weather.get("daily", {})
    daily_forecast = []
    for i, date in enumerate(daily_keys.get("time", [])):
        daily_forecast.append({
            "date":                        date,
            "temperature_2m_max":          daily_keys["temperature_2m_max"][i],
            "temperature_2m_min":          daily_keys["temperature_2m_min"][i],
            "precipitation_sum":           daily_keys["precipitation_sum"][i],
            "precipitation_probability_max": daily_keys["precipitation_probability_max"][i],
            "weathercode":                 daily_keys["weathercode"][i],
            "uv_index_max":                daily_keys.get("uv_index_max", [None]*7)[i],
            "sunrise":                     daily_keys.get("sunrise", [None]*7)[i],
            "sunset":                      daily_keys.get("sunset", [None]*7)[i],
        })

    hourly_forecast = weather.get("hourly", {})

    # --- Run predictions ---
    watering = predict_watering(moisture_pct, moisture_trend, daily_forecast, last_pump)
    frost    = predict_frost_alerts(hourly_forecast, daily_forecast)
    growth   = predict_growth(device_uid, daily_forecast, light_lux, planting_date)

    return {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "device_uid":      device_uid,
        "location":        {"lat": lat, "lon": lon},
        "current_sensors": {
            "moisture_pct":  moisture_pct,
            "temperature_c": temperature,
            "light_lux":     light_lux,
        },
        "watering":        watering,
        "frost_alerts":    frost,
        "growth":          growth,
        "weather_forecast": daily_forecast,
    }