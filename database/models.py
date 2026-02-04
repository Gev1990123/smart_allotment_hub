from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    JSON,
    Boolean,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()

# -------------------------
# Sites
# -------------------------
class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    site_code = Column(String, unique=True, nullable=False)
    friendly_name = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    readings = relationship("SensorData", back_populates="site")
    devices = relationship("Device", back_populates="site")

# -------------------------
# Devices
# -------------------------
class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    uid = Column(String, unique=True, nullable=False)       
    name = Column(String, nullable=True)                    
    active = Column(Boolean, default=False)                
    last_seen = Column(DateTime(timezone=True), nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="SET NULL"))

    sensors = relationship("Sensor", back_populates="device")
    site = relationship("Site", back_populates="devices")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# -------------------------
# Sensors
# -------------------------

class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (UniqueConstraint("device_id", "sensor_name", name="uq_device_sensor"),)

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    sensor_name = Column(String, nullable=False)   # e.g. "soil_moisture"
    sensor_type = Column(String, nullable=False)   # e.g. "moisture", "temperature"
    unit = Column(String, nullable=True)           # e.g. "%"
    last_value = Column(Float, nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="sensors")

# -------------------------
# Sensors Data
# -------------------------
class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True)

    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)

    time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    sensor_id = Column(String, nullable=False)
    sensor_name = Column(String, nullable=False)     # e.g. "soil_moisture"
    sensor_type = Column(String, nullable=False)     # e.g. "moisture", "temperature"
    value = Column(Float, nullable=False)     # e.g. 42.5
    unit = Column(String, nullable=True)             # e.g. "%"

    raw = Column(JSON)

    site = relationship("Site", back_populates="readings")
    device = relationship("Device")