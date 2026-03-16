from pydantic import BaseModel
from typing import Optional

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
    plant_profile_id: int

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