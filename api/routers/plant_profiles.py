from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from dependencies import get_current_user
from models import PlantProfileCreate, PlantProfileUpdate
from db import get_connection

router = APIRouter(prefix="/api/plant-profiles", tags=["plant_profiles"])

@router.get("")
async def list_plant_profiles(current_user: Dict = Depends(get_current_user)):
    """
    Return all plant profiles with emoji + count of sensors currently
    assigned to each profile.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                pp.id,
                pp.name,
                pp.moisture_min,
                pp.moisture_max,
                pp.description,
                COALESCE(pp.emoji, '🌱')        AS emoji,
                COUNT(spa.sensor_id)::int         AS sensor_count
            FROM plant_profiles pp
            LEFT JOIN sensor_plant_assignments spa ON spa.plant_profile_id = pp.id
            GROUP BY pp.id
            ORDER BY pp.name;
        """)
        rows = cur.fetchall()
        return {"plant_profiles": [
            {
                "id":           r[0],
                "name":         r[1],
                "moisture_min": float(r[2]),
                "moisture_max": float(r[3]),
                "description":  r[4],
                "emoji":        r[5],
                "sensor_count": r[6],
            }
            for r in rows
        ]}
    finally:
        conn.close()

@router.post("")
async def create_plant_profile(body: PlantProfileCreate, current_user: Dict = Depends(get_current_user)):
    """Create a new plant profile. Any authenticated user can create."""
    if body.moisture_min >= body.moisture_max:
        raise HTTPException(status_code=400, detail="moisture_min must be less than moisture_max")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM plant_profiles WHERE name = %s;", (body.name,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"A profile named '{body.name}' already exists")

        cur.execute("""
            INSERT INTO plant_profiles (name, moisture_min, moisture_max, description, emoji)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, moisture_min, moisture_max, description, emoji;
        """, (body.name, body.moisture_min, body.moisture_max, body.description, body.emoji))

        row = cur.fetchone()
        conn.commit()
        return {
            "message": "Plant profile created",
            "plant_profile": {
                "id":           row[0],
                "name":         row[1],
                "moisture_min": float(row[2]),
                "moisture_max": float(row[3]),
                "description":  row[4],
                "emoji":        row[5],
            }
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.put("/{profile_id}")
async def update_plant_profile(
    profile_id: int,
    body: PlantProfileUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Update an existing plant profile."""
    if body.moisture_min >= body.moisture_max:
        raise HTTPException(status_code=400, detail="moisture_min must be less than moisture_max")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM plant_profiles WHERE id = %s;", (profile_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Plant profile not found")

        cur.execute(
            "SELECT id FROM plant_profiles WHERE name = %s AND id != %s;",
            (body.name, profile_id)
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"A profile named '{body.name}' already exists")

        cur.execute("""
            UPDATE plant_profiles
            SET name = %s, moisture_min = %s, moisture_max = %s,
                description = %s, emoji = %s
            WHERE id = %s
            RETURNING id, name, moisture_min, moisture_max, description, emoji;
        """, (body.name, body.moisture_min, body.moisture_max,
              body.description, body.emoji, profile_id))

        updated = cur.fetchone()
        conn.commit()
        return {
            "message": "Plant profile updated",
            "plant_profile": {
                "id":           updated[0],
                "name":         updated[1],
                "moisture_min": float(updated[2]),
                "moisture_max": float(updated[3]),
                "description":  updated[4],
                "emoji":        updated[5],
            }
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/{profile_id}")
async def delete_plant_profile(profile_id: int, current_user: Dict = Depends(get_current_user)):
    """
    Delete a plant profile.
    - The 'General' profile cannot be deleted (it is the system fallback).
    - sensor_plant_assignments are removed by ON DELETE CASCADE.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM plant_profiles WHERE id = %s;", (profile_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Plant profile not found")

        if row[0] == "General":
            raise HTTPException(
                status_code=400,
                detail="The 'General' profile cannot be deleted — it is the system fallback"
            )

        cur.execute("DELETE FROM plant_profiles WHERE id = %s;", (profile_id,))
        conn.commit()
        return {"message": f"Plant profile '{row[0]}' deleted"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()