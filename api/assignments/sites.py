from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Dict
from dependencies import require_sys_admin_dep
from models import SiteCreate, SiteInfo
from db import get_connection

router = APIRouter(prefix="/api", tags=["sites"])

@router.get("/sites")
def list_sites():
    """Return all registered sites (unfiltered — used for dropdowns etc.)"""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT site_code, friendly_name, id FROM sites WHERE site_code IS NOT NULL ORDER BY site_code;")
        rows = cur.fetchall()
        sites = [{"site_code": row[0], "friendly_name": row[1], "id": row[2]} for row in rows]

        conn.close()
        return {"sites": sites}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if conn:
            conn.close()

@router.post("/site/register", response_model=SiteInfo)
def register_site(site: SiteCreate, admin: Dict = Depends(require_sys_admin_dep)):
    """Register a new site — sys_admin only"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT site_code, friendly_name FROM sites WHERE site_code = %s;", (site.site_code,))
    row = cur.fetchone()
    if row:
        conn.close()
        raise HTTPException(status_code=400, detail="Site already registered")

    cur.execute("""
        INSERT INTO sites (site_code, friendly_name)
        VALUES (%s, %s)
        RETURNING site_code, friendly_name;
    """, (site.site_code, site.friendly_name))

    new_site = cur.fetchone()
    conn.commit()
    conn.close()

    return {
        "site_code": new_site[0],
        "friendly_name": new_site[1],
    }