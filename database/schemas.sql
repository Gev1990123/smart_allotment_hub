----------------------------------------------------------------------
-- Smart Allotment PostgreSQL Schema
-- Long-table format: one sensor per row
----------------------------------------------------------------------

DROP TABLE IF EXISTS pump_events;
DROP TABLE IF EXISTS sensor_data;
DROP TABLE IF EXISTS sites;

----------------------------------------------------------------------
-- Sites
----------------------------------------------------------------------

CREATE TABLE sites (
    id SERIAL PRIMARY KEY,
    site_code VARCHAR(50) UNIQUE NOT NULL,
    friendly_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

----------------------------------------------------------------------
-- Sensor Data (one row per sensor reading)
----------------------------------------------------------------------

CREATE TABLE sensor_data (
    id BIGSERIAL PRIMARY KEY,

    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,

    -- Device identifier (Raspberry Pi, ESP32, etc.)
    device_id VARCHAR(50) NOT NULL,

    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Your requested data structure:
    sensor_name VARCHAR(50) NOT NULL,        -- e.g. "soil_moisture"
    sensor_value DOUBLE PRECISION NOT NULL,  -- e.g. "42.5"
    unit VARCHAR(20),                        -- e.g. "%"

    raw JSONB
);

CREATE INDEX idx_sensor_data_site_time ON sensor_data(site_id, timestamp);
CREATE INDEX idx_sensor_data_device_time ON sensor_data(device_id, timestamp);
CREATE INDEX idx_sensor_name ON sensor_data(sensor_name);

----------------------------------------------------------------------
-- Pump Events
----------------------------------------------------------------------

CREATE TABLE pump_events (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action VARCHAR(10) NOT NULL,
    triggered_by VARCHAR(50)
);

CREATE INDEX idx_pump_events_site_time ON pump_events(site_id, event_time);
