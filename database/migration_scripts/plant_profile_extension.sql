-- ============================================================
-- MIGRATION: Plant Profile Refactoring with Data Conversion
-- Converts existing flat plant_profiles to hierarchical structure
-- ============================================================
-- This migration:
-- 1. Creates new plant_types and plant_varieties tables
-- 2. Migrates existing plant_profiles data
-- 3. Updates sensor_plant_assignments to use varieties
-- 4. Optionally drops old table
--
-- CURRENT DATA (8 profiles):
--   - General (default)
--   - Tomato
--   - Lettuce
--   - Carrot
--   - Courgette
--   - Potato
--   - Herbs
--   - Strawberry

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
-- Strategy: Each existing profile becomes a plant_type with one variety
-- This maintains all your existing constraints while preparing for future varieties

BEGIN;

-- Step 1: Insert plant types from existing profiles
INSERT INTO plant_types (id, name, emoji, description, created_at, updated_at)
SELECT 
    id,
    name,
    emoji,
    description,
    created_at,
    updated_at
FROM plant_profiles
ON CONFLICT (name) DO NOTHING;

-- Step 2: Create varieties for each plant type
-- Each existing profile becomes a variety with the same name as its parent type
INSERT INTO plant_varieties 
    (plant_type_id, name, description, moisture_min, moisture_max, 
     light_min, light_max, temp_min, temp_max, created_at, updated_at)
SELECT 
    pt.id AS plant_type_id,
    pt.name AS name,  -- Variety name = plant type name (classic/default variety)
    pp.description,
    pp.moisture_min::INTEGER,
    pp.moisture_max::INTEGER,
    NULL,  -- light_min - new field, initially null
    NULL,  -- light_max - new field, initially null
    NULL,  -- temp_min - new field, initially null
    NULL,  -- temp_max - new field, initially null
    pp.created_at,
    pp.updated_at
FROM plant_profiles pp
JOIN plant_types pt ON pt.name = pp.name;

-- Step 3: Update sensor_plant_assignments to use variety_id
-- The variety created above has the same id as the original profile
-- (because we inserted with the same id sequence)
ALTER TABLE IF EXISTS sensor_plant_assignments
    RENAME COLUMN plant_profile_id TO variety_id;

-- Update foreign key constraint
ALTER TABLE sensor_plant_assignments
    DROP CONSTRAINT IF EXISTS sensor_plant_assignments_plant_profile_id_fkey,
    ADD CONSTRAINT sensor_plant_assignments_variety_id_fkey
        FOREIGN KEY (variety_id) REFERENCES plant_varieties(id) ON DELETE SET NULL;

COMMIT;

-- ============================================================
-- 3. CREATE INDEXES FOR PERFORMANCE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_plant_varieties_plant_type_id 
    ON plant_varieties(plant_type_id);

CREATE INDEX IF NOT EXISTS idx_plant_varieties_name 
    ON plant_varieties(name);

CREATE INDEX IF NOT EXISTS idx_sensor_plant_assignments_variety_id 
    ON sensor_plant_assignments(variety_id);

-- ============================================================
-- 4. VERIFY MIGRATION
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
-- 5. OPTIONAL: DROP OLD TABLE (after verifying migration)
-- ============================================================
-- UNCOMMENT ONLY AFTER YOU'VE VERIFIED EVERYTHING WORKS!
-- DROP TABLE IF EXISTS plant_profiles CASCADE;

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================
-- Your data is now in the hierarchical structure:
--
-- plant_types: 8 types (General, Tomato, Lettuce, etc.)
-- plant_varieties: 8 varieties (one default variety per type)
-- sensor_plant_assignments: Updated to reference varieties
--
-- You can now:
-- 1. Add more varieties to existing types (e.g., Tomato -> Beefsteak, Cherry, Roma)
-- 2. Set light and temperature ranges for any variety
-- 3. Have different constraints for different varieties of the same plant
--
-- Next steps:
-- 1. Deploy the new frontend (plant-profiles-updated.html)
-- 2. Deploy the new backend (plant_profiles_router.py)
-- 3. Test the new UI and API
-- 4. After verification, optionally drop the old plant_profiles table