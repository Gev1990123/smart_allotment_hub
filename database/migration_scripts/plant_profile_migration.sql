-- Migration: add emoji column to plant_profiles
-- Run this once against your existing database.
 
ALTER TABLE plant_profiles
    ADD COLUMN IF NOT EXISTS emoji VARCHAR(10) DEFAULT '🌱';
 
-- Seed sensible emojis for the built-in profiles
UPDATE plant_profiles SET emoji = '🍅' WHERE name = 'Tomato';
UPDATE plant_profiles SET emoji = '🥬' WHERE name = 'Lettuce';
UPDATE plant_profiles SET emoji = '🥕' WHERE name = 'Carrot';
UPDATE plant_profiles SET emoji = '🌿' WHERE name = 'Courgette';
UPDATE plant_profiles SET emoji = '🥔' WHERE name = 'Potato';
UPDATE plant_profiles SET emoji = '🌱' WHERE name = 'General';
UPDATE plant_profiles SET emoji = '🌿' WHERE name = 'Herbs';
UPDATE plant_profiles SET emoji = '🍓' WHERE name = 'Strawberry';