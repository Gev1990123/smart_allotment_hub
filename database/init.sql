CREATE TABLE IF NOT EXISTS sensor_data (
    time TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(50),
    sensor_id VARCHAR(50),
    sensor_type VARCHAR(20) NOT NULL,
    value FLOAT,
    unit VARCHAR(10), 
    PRIMARY KEY (time, device_id, sensor_id, sensor_type)
);

CREATE INDEX idx_sensor_data_device_time ON sensor_data(device_id, time DESC);
CREATE INDEX idx_sensor_data_device_type ON sensor_data(device_id, sensor_type);