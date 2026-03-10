-- =============================================================
-- MIGRATION: Add plant profile support
-- Plain Postgres — no TimescaleDB required.
-- Safe to re-run (uses IF NOT EXISTS throughout).
-- Run with:
--   cat migrate_plant_profiles.sql | docker compose exec -T database psql -U mqtt -d sensors
-- =============================================================

-- Plant profiles table
CREATE TABLE IF NOT EXISTS plant_profiles (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(100) UNIQUE NOT NULL,
    moisture_min NUMERIC(5,2) NOT NULL,
    moisture_max NUMERIC(5,2) NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default profiles
INSERT INTO plant_profiles (name, moisture_min, moisture_max, description) VALUES
    ('General',    30, 70, 'Safe default for unknown plants'),
    ('Tomato',     50, 75, 'Consistent moisture, dislikes drying out'),
    ('Lettuce',    60, 80, 'Likes it consistently moist'),
    ('Carrot',     35, 60, 'Dislikes waterlogging'),
    ('Courgette',  50, 70, 'Steady moisture during fruiting'),
    ('Potato',     40, 65, 'Moderate, avoid soggy soil'),
    ('Herbs',      25, 50, 'Prefer drier conditions'),
    ('Strawberry', 50, 70, 'Even moisture, avoid crown rot')
ON CONFLICT (name) DO NOTHING;

-- Link sensors to plant profiles (one profile per moisture sensor)
CREATE TABLE IF NOT EXISTS sensor_plant_assignments (
    sensor_id        INT PRIMARY KEY REFERENCES sensors(id) ON DELETE CASCADE,
    plant_profile_id INT NOT NULL REFERENCES plant_profiles(id),
    assigned_at      TIMESTAMPTZ DEFAULT NOW(),
    assigned_by      INT REFERENCES users(id)
);

-- Moisture event log
CREATE TABLE IF NOT EXISTS moisture_events (
    id             BIGSERIAL PRIMARY KEY,
    sensor_id      INT NOT NULL REFERENCES sensors(id),
    device_id      INT NOT NULL REFERENCES devices(id),
    site_id        INT NOT NULL REFERENCES sites(id),
    reading        NUMERIC(5,2) NOT NULL,
    expected_min   NUMERIC(5,2) NOT NULL,
    expected_max   NUMERIC(5,2) NOT NULL,
    status         VARCHAR(10) NOT NULL CHECK (status IN ('too_dry', 'too_wet', 'ok')),
    action_taken   VARCHAR(50),
    last_action_at TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_moisture_events_sensor  ON moisture_events(sensor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moisture_events_created ON moisture_events(created_at DESC);

-- Add missing columns to sensors table if not already present
-- (notes and registered_by are used in app.py but were missing from original schema)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sensors' AND column_name = 'notes'
    ) THEN
        ALTER TABLE sensors ADD COLUMN notes TEXT;
        RAISE NOTICE 'Added notes column to sensors';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sensors' AND column_name = 'registered_by'
    ) THEN
        ALTER TABLE sensors ADD COLUMN registered_by INT REFERENCES users(id);
        RAISE NOTICE 'Added registered_by column to sensors';
    END IF;
END
$$;