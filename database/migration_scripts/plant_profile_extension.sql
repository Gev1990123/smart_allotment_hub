-- ============================================================
-- MIGRATION: Plant Profile Refactoring with Data Conversion
-- CORRECTED VERSION - Fixes updated_at reference issue
-- ============================================================

-- ============================================================
-- 1. CREATE NEW TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS plant_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    emoji VARCHAR(10) DEFAULT '🌱',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plant_varieties (
    id SERIAL PRIMARY KEY,
    plant_type_id INTEGER NOT NULL REFERENCES plant_types(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    moisture_min INTEGER NOT NULL DEFAULT 30 CHECK (moisture_min >= 0 AND moisture_min <= 100),
    moisture_max INTEGER NOT NULL DEFAULT 70 CHECK (moisture_max >= 0 AND moisture_max <= 100),
    light_min DECIMAL(8, 2),
    light_max DECIMAL(8, 2),
    temp_min DECIMAL(5, 2),
    temp_max DECIMAL(5, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_moisture_range CHECK (moisture_min < moisture_max),
    CONSTRAINT valid_light_range CHECK (light_min IS NULL OR light_max IS NULL OR light_min < light_max),
    CONSTRAINT valid_temp_range CHECK (temp_min IS NULL OR temp_max IS NULL OR temp_min < temp_max),
    UNIQUE(plant_type_id, name)
);

-- ============================================================
-- 2. MIGRATE DATA FROM plant_profiles
-- ============================================================

BEGIN;

-- Step 1: Insert plant types from existing profiles
INSERT INTO plant_types (name, emoji, description, created_at)
SELECT 
    name,
    emoji,
    description,
    created_at
FROM plant_profiles
ON CONFLICT (name) DO NOTHING;

-- Step 2: Create varieties for each plant type
-- Each existing profile becomes a variety with the same name as its parent type
INSERT INTO plant_varieties 
    (plant_type_id, name, description, moisture_min, moisture_max, created_at)
SELECT 
    pt.id AS plant_type_id,
    pt.name AS name,  -- Variety name = plant type name (classic/default variety)
    pp.description,
    pp.moisture_min::INTEGER,
    pp.moisture_max::INTEGER,
    pp.created_at
FROM plant_profiles pp
JOIN plant_types pt ON pt.name = pp.name;

COMMIT;

-- ============================================================
-- 3. UPDATE SENSOR_PLANT_ASSIGNMENTS TABLE
-- ============================================================

-- Step 3: Rename column plant_profile_id to variety_id
ALTER TABLE IF EXISTS sensor_plant_assignments
    RENAME COLUMN plant_profile_id TO variety_id;

-- Step 4: Update foreign key constraint
ALTER TABLE IF EXISTS sensor_plant_assignments
    DROP CONSTRAINT IF EXISTS sensor_plant_assignments_plant_profile_id_fkey;

ALTER TABLE IF EXISTS sensor_plant_assignments
    ADD CONSTRAINT sensor_plant_assignments_variety_id_fkey
        FOREIGN KEY (variety_id) REFERENCES plant_varieties(id) ON DELETE SET NULL;

-- ============================================================
-- 4. CREATE INDEXES FOR PERFORMANCE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_plant_varieties_plant_type_id 
    ON plant_varieties(plant_type_id);

CREATE INDEX IF NOT EXISTS idx_plant_varieties_name 
    ON plant_varieties(name);

CREATE INDEX IF NOT EXISTS idx_sensor_plant_assignments_variety_id 
    ON sensor_plant_assignments(variety_id);

-- ============================================================
-- 5. VERIFY MIGRATION
-- ============================================================

-- Count plant types created
-- SELECT COUNT(*) AS plant_types_count FROM plant_types;
-- Expected: 8

-- Count varieties created
-- SELECT COUNT(*) AS varieties_count FROM plant_varieties;
-- Expected: 8

-- View the new structure
-- SELECT pt.name AS plant_type, pv.name AS variety, pv.moisture_min, pv.moisture_max
-- FROM plant_types pt
-- JOIN plant_varieties pv ON pv.plant_type_id = pt.id
-- ORDER BY pt.name, pv.name;

-- Check sensor assignments are still valid
-- SELECT COUNT(*) AS sensor_count FROM sensor_plant_assignments WHERE variety_id IS NOT NULL;

-- ============================================================
-- 6. OPTIONAL: DROP OLD TABLE (after verifying migration)
-- ============================================================
-- UNCOMMENT ONLY AFTER YOU'VE VERIFIED EVERYTHING WORKS!
-- DROP TABLE IF EXISTS plant_profiles CASCADE;

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================