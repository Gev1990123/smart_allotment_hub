-- ============================================
-- MIGRATION: Add Sowing Information to plant_varieties
-- ============================================

-- Add sowing type column (indoors, outdoors, both)
ALTER TABLE plant_varieties
ADD COLUMN sow_type VARCHAR(20) NOT NULL DEFAULT 'both' 
CHECK (sow_type IN ('indoors', 'outdoors', 'both'));

-- Add sowing window (month of year, 1-12)
ALTER TABLE plant_varieties
ADD COLUMN sow_month_start INTEGER 
CHECK (sow_month_start >= 1 AND sow_month_start <= 12);

ALTER TABLE plant_varieties
ADD COLUMN sow_month_end INTEGER 
CHECK (sow_month_end >= 1 AND sow_month_end <= 12);

-- Add days to germination
ALTER TABLE plant_varieties
ADD COLUMN days_to_germinate INTEGER;

-- Add days from sowing to transplant readiness
ALTER TABLE plant_varieties
ADD COLUMN days_to_transplant_ready INTEGER;

-- Add days from transplant to harvest
ALTER TABLE plant_varieties
ADD COLUMN days_to_harvest INTEGER;

-- Add sow depth in cm
ALTER TABLE plant_varieties
ADD COLUMN sow_depth_cm DECIMAL(5, 2);

-- Add spacing between seeds/seedlings in cm
ALTER TABLE plant_varieties
ADD COLUMN spacing_cm DECIMAL(5, 2);

-- Add constraint for valid sow month range
ALTER TABLE plant_varieties
ADD CONSTRAINT valid_sow_months 
CHECK (sow_month_start IS NULL OR sow_month_end IS NULL OR sow_month_start <= sow_month_end);

-- Add boolean flags
ALTER TABLE plant_varieties
ADD COLUMN can_direct_sow BOOLEAN DEFAULT TRUE;

ALTER TABLE plant_varieties
ADD COLUMN prefers_transplant BOOLEAN DEFAULT FALSE;

-- Update the updated_at timestamp
UPDATE plant_varieties SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NOT NULL;