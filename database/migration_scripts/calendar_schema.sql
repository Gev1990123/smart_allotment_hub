-- ============================================
-- GARDENING CALENDAR SCHEMA
-- ============================================

-- ============================================
-- CROP PROFILES (extend plant_varieties)
-- ============================================
-- Add timing columns to plant_varieties if not already present
ALTER TABLE plant_varieties
ADD COLUMN IF NOT EXISTS hardiness_zone VARCHAR(10);

-- ============================================
-- COMPANION PLANTS
-- ============================================
CREATE TABLE IF NOT EXISTS companion_plants (
    id SERIAL PRIMARY KEY,
    plant_variety_id_a INT NOT NULL REFERENCES plant_varieties(id) ON DELETE CASCADE,
    plant_variety_id_b INT NOT NULL REFERENCES plant_varieties(id) ON DELETE CASCADE,
    relationship VARCHAR(20) NOT NULL CHECK (relationship IN ('companion', 'antagonist')),
    benefit_for_a TEXT,
    benefit_for_b TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(plant_variety_id_a, plant_variety_id_b, relationship),
    CONSTRAINT different_plants CHECK (plant_variety_id_a != plant_variety_id_b)
);

CREATE INDEX IF NOT EXISTS idx_companion_plants_variety_a ON companion_plants(plant_variety_id_a);
CREATE INDEX IF NOT EXISTS idx_companion_plants_variety_b ON companion_plants(plant_variety_id_b);

-- ============================================
-- SUCCESSION CROPS (for rotational planting)
-- ============================================
CREATE TABLE IF NOT EXISTS succession_crops (
    id SERIAL PRIMARY KEY,
    crop_variety_id INT NOT NULL REFERENCES plant_varieties(id) ON DELETE CASCADE,
    succession_order INT NOT NULL,
    days_after_previous INT NOT NULL DEFAULT 30,
    description VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_succession_crops_variety ON succession_crops(crop_variety_id);

-- ============================================
-- CROP SEASONS / SOWING WINDOWS
-- ============================================
CREATE TABLE IF NOT EXISTS crop_seasons (
    id SERIAL PRIMARY KEY,
    plant_variety_id INT NOT NULL REFERENCES plant_varieties(id) ON DELETE CASCADE,
    season_name VARCHAR(100),  -- e.g. "Spring", "Summer", "Fall", "Winter"
    sow_month_start INT NOT NULL CHECK (sow_month_start >= 1 AND sow_month_start <= 12),
    sow_month_end INT NOT NULL CHECK (sow_month_end >= 1 AND sow_month_end <= 12),
    transplant_month_start INT,
    transplant_month_end INT,
    harvest_month_start INT NOT NULL CHECK (harvest_month_start >= 1 AND harvest_month_start <= 12),
    harvest_month_end INT NOT NULL CHECK (harvest_month_end >= 1 AND harvest_month_end <= 12),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(plant_variety_id, season_name)
);

CREATE INDEX IF NOT EXISTS idx_crop_seasons_variety ON crop_seasons(plant_variety_id);

-- ============================================
-- PLANTED CROPS (garden planting log)
-- ============================================
CREATE TABLE IF NOT EXISTS planted_crops (
    id SERIAL PRIMARY KEY,
    site_id INT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    plant_variety_id INT NOT NULL REFERENCES plant_varieties(id),
    bed_location VARCHAR(255),  -- e.g., "Bed A", "Raised Bed 3"
    seed_start_date DATE NOT NULL,
    transplant_date DATE,
    plant_out_date DATE,
    expected_harvest_date DATE,
    actual_harvest_date DATE,
    quantity_planted INT DEFAULT 1,
    notes TEXT,
    status VARCHAR(20) DEFAULT 'planning' CHECK (status IN ('planning', 'seeding', 'growing', 'transplanted', 'harvested', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_planted_crops_site ON planted_crops(site_id);
CREATE INDEX IF NOT EXISTS idx_planted_crops_variety ON planted_crops(plant_variety_id);
CREATE INDEX IF NOT EXISTS idx_planted_crops_seed_start ON planted_crops(seed_start_date);
CREATE INDEX IF NOT EXISTS idx_planted_crops_status ON planted_crops(status);

-- ============================================
-- PLANTING NOTES / EVENTS
-- ============================================
CREATE TABLE IF NOT EXISTS planting_events (
    id SERIAL PRIMARY KEY,
    planted_crop_id INT NOT NULL REFERENCES planted_crops(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,  -- 'germinated', 'thinned', 'watered', 'harvested', 'note'
    event_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by INT REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_planting_events_crop ON planting_events(planted_crop_id);
CREATE INDEX IF NOT EXISTS idx_planting_events_date ON planting_events(event_date);

-- ============================================
-- SAMPLE DATA — CROP TIMINGS
-- ============================================

-- Update tomato variety with timings
UPDATE plant_varieties 
SET 
    days_to_germinate = 5,
    days_to_transplant_ready = 35,
    days_to_harvest = 65,
    can_direct_sow = FALSE,
    prefers_transplant = TRUE,
    min_temp_celsius = 15,
    max_temp_celsius = 35
WHERE plant_type_id = 2 AND name = 'Tomato';

-- Update lettuce variety with timings
UPDATE plant_varieties 
SET 
    days_to_germinate = 7,
    days_to_transplant_ready = 20,
    days_to_harvest = 40,
    can_direct_sow = TRUE,
    prefers_transplant = FALSE
WHERE plant_type_id = 3 AND name = 'Lettuce';

-- Update carrot variety with timings
UPDATE plant_varieties 
SET 
    days_to_germinate = 10,
    days_to_transplant_ready = 0,
    days_to_harvest = 70,
    can_direct_sow = TRUE,
    prefers_transplant = FALSE
WHERE plant_type_id = 4 AND name = 'Carrot';

-- Update courgette variety with timings
UPDATE plant_varieties 
SET 
    days_to_germinate = 5,
    days_to_transplant_ready = 25,
    days_to_harvest = 55,
    can_direct_sow = TRUE,
    prefers_transplant = FALSE,
    min_temp_celsius = 15
WHERE plant_type_id = 5 AND name = 'Courgette';

-- Update potato variety with timings
UPDATE plant_varieties 
SET 
    days_to_germinate = 14,
    days_to_transplant_ready = 0,
    days_to_harvest = 75,
    can_direct_sow = TRUE,
    prefers_transplant = FALSE
WHERE plant_type_id = 6 AND name = 'Potato';

-- Insert crop seasons for tomato (spring/summer sowing)
INSERT INTO crop_seasons (plant_variety_id, season_name, sow_month_start, sow_month_end, transplant_month_start, transplant_month_end, harvest_month_start, harvest_month_end)
SELECT id, 'Spring', 2, 3, 4, 5, 6, 9 FROM plant_varieties WHERE plant_type_id = 2 AND name = 'Tomato'
ON CONFLICT (plant_variety_id, season_name) DO NOTHING;

INSERT INTO crop_seasons (plant_variety_id, season_name, sow_month_start, sow_month_end, transplant_month_start, transplant_month_end, harvest_month_start, harvest_month_end)
SELECT id, 'Spring', 3, 4, NULL, NULL, 4, 6 FROM plant_varieties WHERE plant_type_id = 3 AND name = 'Lettuce'
ON CONFLICT (plant_variety_id, season_name) DO NOTHING;

INSERT INTO crop_seasons (plant_variety_id, season_name, sow_month_start, sow_month_end, transplant_month_start, transplant_month_end, harvest_month_start, harvest_month_end)
SELECT id, 'Spring', 3, 5, NULL, NULL, 6, 8 FROM plant_varieties WHERE plant_type_id = 4 AND name = 'Carrot'
ON CONFLICT (plant_variety_id, season_name) DO NOTHING;

-- Insert some companion plant relationships
INSERT INTO companion_plants (plant_variety_id_a, plant_variety_id_b, relationship, benefit_for_a, benefit_for_b, notes)
SELECT 
    (SELECT id FROM plant_varieties WHERE plant_type_id = 2 LIMIT 1),
    (SELECT id FROM plant_varieties WHERE plant_type_id = 7 LIMIT 1),
    'companion',
    'Herbs repel pests',
    'Tomatoes provide shade',
    'Classic pairing: basil & tomatoes'
ON CONFLICT DO NOTHING;

-- Insert succession crop example for lettuce
INSERT INTO succession_crops (crop_variety_id, succession_order, days_after_previous, description, notes)
SELECT 
    id,
    1,
    21,
    'Second planting of lettuce',
    'Succession sow every 3 weeks for continuous harvest'
FROM plant_varieties WHERE plant_type_id = 3 AND name = 'Lettuce'
ON CONFLICT DO NOTHING;

-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON TABLE planted_crops IS 'Garden planting log — records when crops are sown and transplanted';
COMMENT ON TABLE crop_seasons IS 'Sowing windows for each variety by season';
COMMENT ON TABLE companion_plants IS 'Beneficial and antagonistic plant relationships';
COMMENT ON TABLE planting_events IS 'Timeline events for each planted crop (germinated, harvested, etc.)';