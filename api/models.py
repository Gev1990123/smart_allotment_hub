from pydantic import BaseModel
from typing import Optional, Dict
from datetime import date

class DeviceCreate(BaseModel):
    uid: str
    name: str | None = None
    site_id: int | None = None

class DeviceInfo(BaseModel):
    uid: str
    name: str | None
    active: bool
    last_seen: str | None
    site_id: int | None

class SiteCreate(BaseModel):
    site_code: str
    friendly_name: str | None = None

class SiteInfo(BaseModel):
    site_code: str
    friendly_name: str | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: str | None = None
    role: str = "user"

class UserUpdate(BaseModel):
    email: str
    full_name: str | None = None
    role: str = "user"
    password: str | None = None  # Optional — only update if provided

class ApiTokenCreate(BaseModel):
    name: str
    description: str | None = None
    scopes: list[str] = []
    expires_days: int | None = None
    device_uid: str | None = None  # If set, creates a device token instead of a user token

class SensorDataSubmit(BaseModel):
    sensor_name: str
    sensor_value: float
    unit: str | None = None
    sensor_type: str | None = None

class SensorRegister(BaseModel):
    device_uid: str
    sensor_name: str
    sensor_type: str
    unit: str | None = None
    notes: str | None = None
    zone_name: str | None = None

class SensorInfo(BaseModel):
    id: int
    device_id: int
    device_uid: str
    sensor_name: str
    sensor_type: str
    unit: str | None
    active: bool
    last_value: float | None
    last_seen: str | None
    notes: str | None
    created_at: str | None

class PumpCommand(BaseModel):
    action: str  # "on" or "off"
    seconds: int | None = None  # Required when action == "run"

class SensorPlantAssign(BaseModel):
    variety_id: int

class SensorZoneAssign(BaseModel):
    zone_name: str | None = None

class PlantProfileCreate(BaseModel):
    name: str
    moisture_min: float
    moisture_max: float
    description: Optional[str] = None
    emoji: Optional[str] = "🌱"

class PlantProfileUpdate(PlantProfileCreate):
    pass

class PlantTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    emoji: str = "🌱"

class PlantTypeUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    emoji: str = "🌱"

class VarietyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    moisture_min: int
    moisture_max: int
    light_min: Optional[float] = None
    light_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None

class VarietyUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    moisture_min: int
    moisture_max: int
    light_min: Optional[float] = None
    light_max: Optional[float] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None

# ============================================================
# PLANTED CROPS
# ============================================================
 
class PlantedCropCreate(BaseModel):
    """Request body for creating a new planted crop."""
    site_id: int
    plant_variety_id: int
    bed_location: str
    seed_start_date: str  # ISO format: "2024-03-15"
    quantity_planted: Optional[int] = 1
    notes: Optional[str] = None
 
 
class PlantedCropUpdate(BaseModel):
    """Request body for updating a planted crop."""
    status: Optional[str] = None  # e.g., "seeding", "growing", "harvested"
    plant_out_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    notes: Optional[str] = None
 
 
class PlantedCropResponse(BaseModel):
    """Response for a planted crop."""
    id: int
    site_id: int
    plant_variety_id: int
    crop_name: str
    bed_location: str
    seed_start_date: str
    transplant_date: Optional[str]
    plant_out_date: Optional[str]
    expected_harvest_date: str
    actual_harvest_date: Optional[str]
    quantity_planted: int
    status: str
    days_to_harvest: Optional[int]
    prefers_transplant: bool
    emoji: str
    notes: Optional[str]
    created_at: Optional[str]
 
 
# ============================================================
# PLANTING EVENTS
# ============================================================
 
class PlantingEventCreate(BaseModel):
    """Request body for logging a planting event."""
    event_type: str  # e.g., "germinated", "thinned", "watered", "harvested", "note"
    event_date: str  # ISO format: "2024-04-15"
    notes: Optional[str] = None
 
 
class PlantingEventResponse(BaseModel):
    """Response for a planting event."""
    id: int
    event_type: str
    event_date: str
    notes: Optional[str]
    created_at: Optional[str]
    created_by: Optional[int]
 
 
# ============================================================
# COMPANION PLANTS
# ============================================================
 
class CompanionPlantCreate(BaseModel):
    """Request body for creating a companion plant relationship."""
    plant_variety_id_a: int
    plant_variety_id_b: int
    relationship: str  # "companion" or "antagonist"
    benefit_for_a: Optional[str] = None
    benefit_for_b: Optional[str] = None
    notes: Optional[str] = None
 
 
class CompanionPlantQuery(BaseModel):
    """Response for companion plant query."""
    id: int
    companion_name: str
    benefit: Optional[str]
    relationship: str
    notes: Optional[str]
 
 
# ============================================================
# CROP TIMELINES & SEASONS
# ============================================================
 
class CropSeasonResponse(BaseModel):
    """Response for a crop season."""
    season: str
    harvest_month_start: int
    harvest_month_end: int
 
 
class CropTimelineResponse(BaseModel):
    """Response for a crop timeline calculation."""
    variety_id: int
    variety_name: str
    seed_start_date: str
    germination_date: str
    germination_days: int
    transplant_ready_date: Optional[str]
    transplant_ready_days: int
    expected_harvest_date: str
    harvest_days_from_seed: int
    prefers_transplant: bool
    can_direct_sow: bool
    seasons: list[CropSeasonResponse]
 
 
# ============================================================
# SUCCESSION CROPS
# ============================================================
 
class SuccessionCropResponse(BaseModel):
    """Response for a succession crop suggestion."""
    id: int
    succession_order: int
    days_after_previous: int
    description: str
    notes: Optional[str]
 
 
# ============================================================
# CALENDAR VIEW
# ============================================================
 
class CalendarCropResponse(BaseModel):
    """Response for crops in calendar view."""
    id: int
    crop_name: str
    emoji: str
    bed_location: str
    seed_start_date: str
    transplant_date: Optional[str]
    plant_out_date: Optional[str]
    expected_harvest_date: str
    actual_harvest_date: Optional[str]
    quantity_planted: int
 
 
class CalendarViewResponse(BaseModel):
    """Response for month calendar view."""
    site_id: int
    month: int
    year: int
    crops_by_status: Dict[str, list[CalendarCropResponse]]