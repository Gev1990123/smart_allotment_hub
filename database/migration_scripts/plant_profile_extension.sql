-- Migration: add further columns to the plant profile table
-- Run this once against your existing database.
 
ALTER TABLE plant_profiles
    ADD COLUMN IF NOT EXISTS variety VARCHAR(100),
    ADD COLUMN IF NOT EXISTS light_min DECIMAL(5,2),
    ADD COLUMN IF NOT EXISTS light_max DECIMAL(5,2),
    ADD COLUMN IF NOT EXISTS temp_min DECIMAL(5,2),
    ADD COLUMN IF NOT EXISTS temp_max DECIMAL(5,2),
 