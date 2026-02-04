-- -------------------------
-- SITES
-- -------------------------
CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    site_code VARCHAR(50) UNIQUE NOT NULL,
    friendly_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------
-- DEVICES
-- -------------------------
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    uid VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255),
    active BOOLEAN DEFAULT FALSE,
    last_seen TIMESTAMPTZ,
    site_id INT REFERENCES sites(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------
-- SENSORS
-- -------------------------
CREATE TABLE IF NOT EXISTS sensors (
    id SERIAL PRIMARY KEY,
    device_id INT NOT NULL REFERENCES devices(id),
    sensor_name VARCHAR(50) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    unit VARCHAR(10),
    last_value FLOAT,
    last_seen TIMESTAMPTZ,
    CONSTRAINT uq_device_sensor UNIQUE(device_id, sensor_name)
);

-- -------------------------
-- SENSOR DATA (readings)
-- -------------------------
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    site_id INT NOT NULL REFERENCES sites(id),
    device_id INT NOT NULL REFERENCES devices(id),
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sensor_id VARCHAR(50),
    sensor_name VARCHAR(50) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    value FLOAT,
    unit VARCHAR(10), 
    raw JSON
);


CREATE INDEX idx_sensor_data_device_time ON sensor_data(device_id, time DESC);
CREATE INDEX idx_sensor_data_device_type ON sensor_data(device_id, sensor_type);
CREATE INDEX idx_sensor_data_device_type_time ON sensor_data(device_id, sensor_type, time DESC);