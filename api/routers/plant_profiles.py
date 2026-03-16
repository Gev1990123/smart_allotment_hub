from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from dependencies import get_current_user
from models import PlantProfileCreate, PlantProfileUpdate, PlantTypeCreate, PlantTypeUpdate, VarietyCreate, VarietyUpdate
from db import get_connection

router = APIRouter(prefix="/api/plant-profiles", tags=["plant_profiles"])

# ============================================================
# PLANT TYPES ENDPOINTS
# ============================================================

@router.get("/types")
async def list_plant_types(current_user: Dict = Depends(get_current_user)):
    """
    Return all plant types with variety count and sensor assignments.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                pt.id,
                pt.name,
                pt.description,
                COALESCE(pt.emoji, '🌱') AS emoji,
                COUNT(DISTINCT pv.id)::int AS variety_count,
                COUNT(DISTINCT spa.sensor_id)::int AS sensor_count
            FROM plant_types pt
            LEFT JOIN plant_varieties pv ON pv.plant_type_id = pt.id
            LEFT JOIN sensor_plant_assignments spa ON spa.variety_id = pv.id
            GROUP BY pt.id, pt.name, pt.description, pt.emoji
            ORDER BY pt.name;
        """)
        rows = cur.fetchall()
        return {
            "plant_types": [
                {
                    "id": r[0],
                    "name": r[1],
                    "description": r[2],
                    "emoji": r[3],
                    "variety_count": r[4],
                    "sensor_count": r[5],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()
 
@router.post("/types")
async def create_plant_type(body: PlantTypeCreate, current_user: Dict = Depends(get_current_user)):
    """Create a new plant type."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM plant_types WHERE name = %s;", (body.name,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"A plant type named '{body.name}' already exists")
 
        cur.execute("""
            INSERT INTO plant_types (name, description, emoji)
            VALUES (%s, %s, %s)
            RETURNING id, name, description, emoji;
        """, (body.name, body.description, body.emoji))
 
        row = cur.fetchone()
        conn.commit()
        return {
            "message": "Plant type created",
            "plant_type": {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "emoji": row[3],
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
 
@router.put("/types/{plant_type_id}")
async def update_plant_type(
    plant_type_id: int,
    body: PlantTypeUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Update a plant type."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM plant_types WHERE id = %s;", (plant_type_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Plant type not found")
 
        cur.execute(
            "SELECT id FROM plant_types WHERE name = %s AND id != %s;",
            (body.name, plant_type_id)
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"A plant type named '{body.name}' already exists")
 
        cur.execute("""
            UPDATE plant_types
            SET name = %s, description = %s, emoji = %s
            WHERE id = %s
            RETURNING id, name, description, emoji;
        """, (body.name, body.description, body.emoji, plant_type_id))
 
        row = cur.fetchone()
        conn.commit()
        return {
            "message": "Plant type updated",
            "plant_type": {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "emoji": row[3],
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
 
@router.delete("/types/{plant_type_id}")
async def delete_plant_type(plant_type_id: int, current_user: Dict = Depends(get_current_user)):
    """
    Delete a plant type and all its varieties.
    Sensor assignments are cleaned up via cascade.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM plant_types WHERE id = %s;", (plant_type_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Plant type not found")
 
        # Delete cascades to varieties and sensor_plant_assignments
        cur.execute("DELETE FROM plant_types WHERE id = %s;", (plant_type_id,))
        conn.commit()
        return {"message": f"Plant type '{row[0]}' and all its varieties deleted"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
 
# ============================================================
# VARIETIES ENDPOINTS
# ============================================================
@router.get("/types/{plant_type_id}/varieties")
async def list_varieties(plant_type_id: int, current_user: Dict = Depends(get_current_user)):
    """
    Return all varieties for a plant type with sensor assignment counts.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # First verify plant type exists
        cur.execute("SELECT id FROM plant_types WHERE id = %s;", (plant_type_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Plant type not found")
 
        cur.execute("""
            SELECT
                pv.id,
                pv.name,
                pv.description,
                pv.moisture_min,
                pv.moisture_max,
                COALESCE(pv.light_min, 0)::float AS light_min,
                COALESCE(pv.light_max, 0)::float AS light_max,
                COALESCE(pv.temp_min, 0)::float AS temp_min,
                COALESCE(pv.temp_max, 0)::float AS temp_max,
                COUNT(spa.sensor_id)::int AS sensor_count
            FROM plant_varieties pv
            LEFT JOIN sensor_plant_assignments spa ON spa.variety_id = pv.id
            WHERE pv.plant_type_id = %s
            GROUP BY pv.id, pv.name, pv.description, pv.moisture_min,
                     pv.moisture_max, pv.light_min, pv.light_max,
                     pv.temp_min, pv.temp_max
            ORDER BY pv.name;
        """, (plant_type_id,))
 
        rows = cur.fetchall()
        return {
            "plant_type_id": plant_type_id,
            "varieties": [
                {
                    "id": r[0],
                    "name": r[1],
                    "description": r[2],
                    "moisture_min": float(r[3]),
                    "moisture_max": float(r[4]),
                    "light_min": r[5] if r[5] else None,
                    "light_max": r[6] if r[6] else None,
                    "temp_min": r[7] if r[7] else None,
                    "temp_max": r[8] if r[8] else None,
                    "sensor_count": r[9],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()
 
@router.post("/types/{plant_type_id}/varieties")
async def create_variety(
    plant_type_id: int,
    body: VarietyCreate,
    current_user: Dict = Depends(get_current_user)
):
    """Create a new variety for a plant type."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if body.moisture_min >= body.moisture_max:
            raise HTTPException(status_code=400, detail="moisture_min must be less than moisture_max")
 
        if body.light_min is not None and body.light_max is not None and body.light_min >= body.light_max:
            raise HTTPException(status_code=400, detail="light_min must be less than light_max")
 
        if body.temp_min is not None and body.temp_max is not None and body.temp_min >= body.temp_max:
            raise HTTPException(status_code=400, detail="temp_min must be less than temp_max")
 
        # Verify plant type exists
        cur.execute("SELECT id FROM plant_types WHERE id = %s;", (plant_type_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Plant type not found")
 
        cur.execute("""
            INSERT INTO plant_varieties
            (plant_type_id, name, description, moisture_min, moisture_max,
             light_min, light_max, temp_min, temp_max)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, description, moisture_min, moisture_max,
                      light_min, light_max, temp_min, temp_max;
        """, (plant_type_id, body.name, body.description, body.moisture_min,
              body.moisture_max, body.light_min, body.light_max,
              body.temp_min, body.temp_max))
 
        row = cur.fetchone()
        conn.commit()
        return {
            "message": "Variety created",
            "variety": {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "moisture_min": float(row[3]),
                "moisture_max": float(row[4]),
                "light_min": float(row[5]) if row[5] else None,
                "light_max": float(row[6]) if row[6] else None,
                "temp_min": float(row[7]) if row[7] else None,
                "temp_max": float(row[8]) if row[8] else None,
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
 
@router.put("/varieties/{variety_id}")
async def update_variety(
    variety_id: int,
    body: VarietyUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Update a variety."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        if body.moisture_min >= body.moisture_max:
            raise HTTPException(status_code=400, detail="moisture_min must be less than moisture_max")
 
        if body.light_min is not None and body.light_max is not None and body.light_min >= body.light_max:
            raise HTTPException(status_code=400, detail="light_min must be less than light_max")
 
        if body.temp_min is not None and body.temp_max is not None and body.temp_min >= body.temp_max:
            raise HTTPException(status_code=400, detail="temp_min must be less than temp_max")
 
        cur.execute("SELECT id FROM plant_varieties WHERE id = %s;", (variety_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Variety not found")
 
        cur.execute("""
            UPDATE plant_varieties
            SET name = %s, description = %s, moisture_min = %s, moisture_max = %s,
                light_min = %s, light_max = %s, temp_min = %s, temp_max = %s
            WHERE id = %s
            RETURNING id, name, description, moisture_min, moisture_max,
                      light_min, light_max, temp_min, temp_max;
        """, (body.name, body.description, body.moisture_min, body.moisture_max,
              body.light_min, body.light_max, body.temp_min, body.temp_max, variety_id))
 
        row = cur.fetchone()
        conn.commit()
        return {
            "message": "Variety updated",
            "variety": {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "moisture_min": float(row[3]),
                "moisture_max": float(row[4]),
                "light_min": float(row[5]) if row[5] else None,
                "light_max": float(row[6]) if row[6] else None,
                "temp_min": float(row[7]) if row[7] else None,
                "temp_max": float(row[8]) if row[8] else None,
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
 
@router.delete("/varieties/{variety_id}")
async def delete_variety(variety_id: int, current_user: Dict = Depends(get_current_user)):
    """
    Delete a variety.
    Sensor assignments are cleaned up via cascade.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM plant_varieties WHERE id = %s;", (variety_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Variety not found")
 
        cur.execute("DELETE FROM plant_varieties WHERE id = %s;", (variety_id,))
        conn.commit()
        return {"message": f"Variety '{row[0]}' deleted"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
 
# ============================================================
# LEGACY ENDPOINTS (for backward compatibility)
# ============================================================
@router.get("")
async def list_plant_profiles(current_user: Dict = Depends(get_current_user)):
    """
    Return a flattened list of all varieties (for backward compatibility with sensors UI).
    Each variety is returned as if it were a profile.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                pv.id,
                pt.name || ' - ' || pv.name AS full_name,
                pv.moisture_min,
                pv.moisture_max,
                pv.description,
                pt.emoji,
                COUNT(spa.sensor_id)::int AS sensor_count
            FROM plant_varieties pv
            JOIN plant_types pt ON pt.id = pv.plant_type_id
            LEFT JOIN sensor_plant_assignments spa ON spa.variety_id = pv.id
            GROUP BY pv.id, pt.name, pv.name, pv.moisture_min, pv.moisture_max,
                     pv.description, pt.emoji
            ORDER BY pt.name, pv.name;
        """)
        rows = cur.fetchall()
        return {
            "plant_profiles": [
                {
                    "id": r[0],
                    "name": r[1],
                    "moisture_min": float(r[2]),
                    "moisture_max": float(r[3]),
                    "description": r[4],
                    "emoji": r[5],
                    "sensor_count": r[6],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()