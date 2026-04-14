from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dependencies import get_current_user
from models import (
    PlantedCropCreate,
    PlantedCropUpdate,
    PlantingEventCreate,
    CompanionPlantQuery
)
from db import get_connection

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

# ============================================================
# PLANTED CROPS ENDPOINTS
# ============================================================

@router.post("/crops/plant")
async def plant_crop(
    body: PlantedCropCreate,
    current_user: Dict = Depends(get_current_user),
):
    """
    Create a new planted crop entry. Calculates transplant, plant-out, and harvest dates
    based on variety timing information.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Fetch variety to get timing info
        cur.execute("""
            SELECT
                days_to_germinate,
                days_to_transplant_ready,
                days_to_harvest,
                prefers_transplant,
                can_direct_sow
            FROM plant_varieties
            WHERE id = %s;
        """, (body.plant_variety_id,))
        
        variety = cur.fetchone()
        if not variety:
            raise HTTPException(status_code=404, detail="Plant variety not found")
        
        days_to_germinate, days_to_transplant, days_to_harvest, prefers_transplant, can_direct_sow = variety
        
        # Calculate key dates
        seed_start = datetime.strptime(body.seed_start_date, "%Y-%m-%d").date()
        germination_date = seed_start + timedelta(days=days_to_germinate or 7)
        transplant_ready_date = seed_start + timedelta(days=(days_to_germinate or 7) + (days_to_transplant or 30))
        expected_harvest_date = seed_start + timedelta(days=(days_to_germinate or 7) + (days_to_harvest or 60))
        
        # Insert the planted crop record
        cur.execute("""
            INSERT INTO planted_crops
            (site_id, user_id, plant_variety_id, bed_location, seed_start_date,
             transplant_date, expected_harvest_date, quantity_planted, notes, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'planning')
            RETURNING
                id, site_id, plant_variety_id, bed_location, seed_start_date,
                transplant_date, expected_harvest_date, quantity_planted, status, created_at;
        """, (
            body.site_id,
            current_user["id"],
            body.plant_variety_id,
            body.bed_location,
            seed_start,
            transplant_ready_date if (prefers_transplant or not can_direct_sow) else None,
            expected_harvest_date,
            body.quantity_planted or 1,
            body.notes
        ))
        
        row = cur.fetchone()
        conn.commit()
        
        return {
            "message": "Crop planted",
            "planted_crop": {
                "id": row[0],
                "site_id": row[1],
                "plant_variety_id": row[2],
                "bed_location": row[3],
                "seed_start_date": str(row[4]),
                "transplant_date": str(row[5]) if row[5] else None,
                "expected_harvest_date": str(row[6]),
                "quantity_planted": row[7],
                "status": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
                "germination_estimate": str(germination_date),
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


@router.get("/crops/site/{site_id}")
async def list_crops_for_site(
    site_id: int,
    current_user: Dict = Depends(get_current_user),
    status: Optional[str] = None,
):
    """
    List all planted crops for a site with variety details and companion plants.
    Optional filter by status (planning, seeding, growing, etc.)
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT
                pc.id,
                pc.plant_variety_id,
                pt.name || ' - ' || pv.name AS crop_name,
                pc.bed_location,
                pc.seed_start_date,
                pc.transplant_date,
                pc.plant_out_date,
                pc.expected_harvest_date,
                pc.actual_harvest_date,
                pc.quantity_planted,
                pc.status,
                pv.days_to_harvest,
                pv.prefers_transplant,
                pt.emoji,
                pc.notes,
                pc.created_at
            FROM planted_crops pc
            JOIN plant_varieties pv ON pv.id = pc.plant_variety_id
            JOIN plant_types pt ON pt.id = pv.plant_type_id
            WHERE pc.site_id = %s
        """
        
        params = [site_id]
        
        if status:
            query += " AND pc.status = %s"
            params.append(status)
        
        query += " ORDER BY pc.seed_start_date DESC;"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        crops = []
        for r in rows:
            crops.append({
                "id": r[0],
                "plant_variety_id": r[1],
                "crop_name": r[2],
                "bed_location": r[3],
                "seed_start_date": str(r[4]),
                "transplant_date": str(r[5]) if r[5] else None,
                "plant_out_date": str(r[6]) if r[6] else None,
                "expected_harvest_date": str(r[7]),
                "actual_harvest_date": str(r[8]) if r[8] else None,
                "quantity_planted": r[9],
                "status": r[10],
                "days_to_harvest": r[11],
                "prefers_transplant": r[12],
                "emoji": r[13],
                "notes": r[14],
                "created_at": r[15].isoformat() if r[15] else None,
            })
        
        return {"crops": crops}
    finally:
        conn.close()


@router.put("/crops/{crop_id}")
async def update_crop(
    crop_id: int,
    body: PlantedCropUpdate,
    current_user: Dict = Depends(get_current_user),
):
    """Update a planted crop (e.g., mark as harvested, update dates)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Verify crop exists
        cur.execute("SELECT id FROM planted_crops WHERE id = %s;", (crop_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Crop not found")
        
        # Build update query
        updates = []
        params = []
        
        if body.status is not None:
            updates.append("status = %s")
            params.append(body.status)
        if body.plant_out_date is not None:
            updates.append("plant_out_date = %s")
            params.append(body.plant_out_date)
        if body.actual_harvest_date is not None:
            updates.append("actual_harvest_date = %s")
            params.append(body.actual_harvest_date)
        if body.notes is not None:
            updates.append("notes = %s")
            params.append(body.notes)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        updates.append("updated_at = NOW()")
        params.append(crop_id)
        
        update_sql = f"""
            UPDATE planted_crops
            SET {", ".join(updates)}
            WHERE id = %s
            RETURNING id, status, plant_out_date, actual_harvest_date, updated_at;
        """
        
        cur.execute(update_sql, params)
        row = cur.fetchone()
        conn.commit()
        
        return {
            "message": "Crop updated",
            "crop": {
                "id": row[0],
                "status": row[1],
                "plant_out_date": str(row[2]) if row[2] else None,
                "actual_harvest_date": str(row[3]) if row[3] else None,
                "updated_at": row[4].isoformat() if row[4] else None,
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


@router.delete("/crops/{crop_id}")
async def delete_crop(
    crop_id: int,
    current_user: Dict = Depends(get_current_user),
):
    """Delete a planted crop."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM (SELECT id, plant_variety_id FROM planted_crops WHERE id = %s) AS pc;", (crop_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Crop not found")
        
        cur.execute("DELETE FROM planted_crops WHERE id = %s;", (crop_id,))
        conn.commit()
        
        return {"message": "Crop deleted"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ============================================================
# COMPANION PLANTS ENDPOINTS
# ============================================================

@router.get("/companions/{plant_variety_id}")
async def get_companions(
    plant_variety_id: int,
    current_user: Dict = Depends(get_current_user),
):
    """
    Get all companion plants for a variety (both beneficial companions and antagonists).
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                cp.id,
                CASE 
                    WHEN cp.plant_variety_id_a = %s THEN pt2.name || ' - ' || pv2.name
                    ELSE pt1.name || ' - ' || pv1.name
                END AS companion_name,
                CASE 
                    WHEN cp.plant_variety_id_a = %s THEN cp.benefit_for_a
                    ELSE cp.benefit_for_b
                END AS benefit,
                cp.relationship,
                cp.notes
            FROM companion_plants cp
            JOIN plant_varieties pv1 ON pv1.id = cp.plant_variety_id_a
            JOIN plant_types pt1 ON pt1.id = pv1.plant_type_id
            JOIN plant_varieties pv2 ON pv2.id = cp.plant_variety_id_b
            JOIN plant_types pt2 ON pt2.id = pv2.plant_type_id
            WHERE cp.plant_variety_id_a = %s OR cp.plant_variety_id_b = %s
            ORDER BY cp.relationship DESC, companion_name;
        """, (plant_variety_id, plant_variety_id, plant_variety_id, plant_variety_id))
        
        rows = cur.fetchall()
        
        companions = []
        for r in rows:
            companions.append({
                "id": r[0],
                "companion_name": r[1],
                "benefit": r[2],
                "relationship": r[3],
                "notes": r[4],
            })
        
        return {"companions": companions}
    finally:
        conn.close()


# ============================================================
# CROP TIMELINE / CALENDAR ENDPOINTS
# ============================================================

@router.get("/timeline/{plant_variety_id}")
async def get_crop_timeline(
    plant_variety_id: int,
    seed_start_date: str,  # ISO format: 2024-03-15
    current_user: Dict = Depends(get_current_user),
):
    """
    Calculate and return the full timeline for a crop from seed start to harvest.
    Returns germination, transplant, and harvest dates.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                id,
                name,
                days_to_germinate,
                days_to_transplant_ready,
                days_to_harvest,
                prefers_transplant,
                can_direct_sow,
                plant_type_id
            FROM plant_varieties
            WHERE id = %s;
        """, (plant_variety_id,))
        
        variety = cur.fetchone()
        if not variety:
            raise HTTPException(status_code=404, detail="Variety not found")
        
        variety_id, name, days_germ, days_trans, days_harv, prefers_trans, can_direct, plant_type_id = variety
        
        # Parse seed start date
        seed_start = datetime.strptime(seed_start_date, "%Y-%m-%d").date()
        
        # Calculate timeline
        days_germ = days_germ or 7
        days_trans = days_trans or 30
        days_harv = days_harv or 60
        
        germination_date = seed_start + timedelta(days=days_germ)
        transplant_ready_date = seed_start + timedelta(days=days_germ + days_trans)
        harvest_date = seed_start + timedelta(days=days_germ + days_harv)
        
        # Fetch crop seasons for this variety
        cur.execute("""
            SELECT season_name, harvest_month_start, harvest_month_end
            FROM crop_seasons
            WHERE plant_variety_id = %s
            ORDER BY season_name;
        """, (plant_variety_id,))
        
        seasons = cur.fetchall()
        
        return {
            "variety_id": variety_id,
            "variety_name": name,
            "seed_start_date": str(seed_start),
            "germination_date": str(germination_date),
            "germination_days": days_germ,
            "transplant_ready_date": str(transplant_ready_date) if (prefers_trans or not can_direct) else None,
            "transplant_ready_days": days_germ + days_trans,
            "expected_harvest_date": str(harvest_date),
            "harvest_days_from_seed": days_germ + days_harv,
            "prefers_transplant": prefers_trans,
            "can_direct_sow": can_direct,
            "seasons": [{"season": s[0], "harvest_month_start": s[1], "harvest_month_end": s[2]} for s in seasons],
        }
    finally:
        conn.close()


@router.get("/succession/{plant_variety_id}")
async def get_succession_suggestions(
    plant_variety_id: int,
    current_user: Dict = Depends(get_current_user),
):
    """
    Get succession planting suggestions for a variety (follow-up crops to plant after harvest).
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                id,
                succession_order,
                days_after_previous,
                description,
                notes
            FROM succession_crops
            WHERE crop_variety_id = %s
            ORDER BY succession_order;
        """, (plant_variety_id,))
        
        rows = cur.fetchall()
        
        succession = []
        for r in rows:
            succession.append({
                "id": r[0],
                "succession_order": r[1],
                "days_after_previous": r[2],
                "description": r[3],
                "notes": r[4],
            })
        
        return {"succession_crops": succession}
    finally:
        conn.close()


# ============================================================
# PLANTING EVENTS
# ============================================================

@router.post("/crops/{crop_id}/events")
async def add_planting_event(
    crop_id: int,
    body: PlantingEventCreate,
    current_user: Dict = Depends(get_current_user),
):
    """Log a planting event (germinated, thinned, harvested, etc.)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Verify crop exists
        cur.execute("SELECT id FROM planted_crops WHERE id = %s;", (crop_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Crop not found")
        
        cur.execute("""
            INSERT INTO planting_events
            (planted_crop_id, event_type, event_date, notes, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, event_type, event_date, notes, created_at;
        """, (crop_id, body.event_type, body.event_date, body.notes, current_user["id"]))
        
        row = cur.fetchone()
        conn.commit()
        
        return {
            "message": "Event logged",
            "event": {
                "id": row[0],
                "event_type": row[1],
                "event_date": str(row[2]),
                "notes": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
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


@router.get("/crops/{crop_id}/events")
async def get_crop_events(
    crop_id: int,
    current_user: Dict = Depends(get_current_user),
):
    """Get all events for a planted crop."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                id,
                event_type,
                event_date,
                notes,
                created_at,
                created_by
            FROM planting_events
            WHERE planted_crop_id = %s
            ORDER BY event_date DESC;
        """, (crop_id,))
        
        rows = cur.fetchall()
        
        events = []
        for r in rows:
            events.append({
                "id": r[0],
                "event_type": r[1],
                "event_date": str(r[2]),
                "notes": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "created_by": r[5],
            })
        
        return {"events": events}
    finally:
        conn.close()


# ============================================================
# CALENDAR VIEW
# ============================================================

@router.get("/view/{site_id}")
async def get_calendar_view(
    site_id: int,
    month: int,
    year: int,
    current_user: Dict = Depends(get_current_user),
):
    """
    Get calendar view for a site — shows all crops and key dates for a given month/year.
    Returns crops grouped by status and their key milestone dates.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                pc.id,
                pc.plant_variety_id,
                pt.name || ' - ' || pv.name AS crop_name,
                pt.emoji,
                pc.bed_location,
                pc.seed_start_date,
                pc.transplant_date,
                pc.plant_out_date,
                pc.expected_harvest_date,
                pc.actual_harvest_date,
                pc.status,
                pc.quantity_planted,
                EXTRACT(MONTH FROM pc.seed_start_date)::int AS seed_month,
                EXTRACT(YEAR FROM pc.seed_start_date)::int AS seed_year
            FROM planted_crops pc
            JOIN plant_varieties pv ON pv.id = pc.plant_variety_id
            JOIN plant_types pt ON pt.id = pv.plant_type_id
            WHERE pc.site_id = %s
            ORDER BY pc.seed_start_date;
        """, (site_id,))
        
        rows = cur.fetchall()
        
        # Filter by month/year and group by status
        calendar_data = {
            "planning": [],
            "seeding": [],
            "growing": [],
            "transplanted": [],
            "harvested": [],
            "failed": [],
        }
        
        for r in rows:
            seed_month = r[12]
            seed_year = r[13]
            
            # Check if crop overlaps with requested month
            if seed_year == year and seed_month == month:
                crop_entry = {
                    "id": r[0],
                    "crop_name": r[2],
                    "emoji": r[3],
                    "bed_location": r[4],
                    "seed_start_date": str(r[5]),
                    "transplant_date": str(r[6]) if r[6] else None,
                    "plant_out_date": str(r[7]) if r[7] else None,
                    "expected_harvest_date": str(r[8]),
                    "actual_harvest_date": str(r[9]) if r[9] else None,
                    "quantity_planted": r[11],
                }
                
                status = r[10]
                if status in calendar_data:
                    calendar_data[status].append(crop_entry)
        
        return {
            "site_id": site_id,
            "month": month,
            "year": year,
            "crops_by_status": calendar_data,
        }
    finally:
        conn.close()