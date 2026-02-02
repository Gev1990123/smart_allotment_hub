from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    JSON,
    ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()

class Site(Base):
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    site_code = Column(String, unique=True, nullable=False)
    friendly_name = Column(String)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    readings = relationship("SensorData", back_populates="site")


class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True)

    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    device_id = Column(String, nullable=False)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Your requested structure:
    sensor_name = Column(String, nullable=False)     # e.g. "soil_moisture"
    sensor_value = Column(Float, nullable=False)     # e.g. 42.5
    unit = Column(String, nullable=True)             # e.g. "%"

    raw = Column(JSON)

    site = relationship("Site", back_populates="readings")
