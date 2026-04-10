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
        active BOOLEAN DEFAULT FALSE,
        unit VARCHAR(10),
        zone_name VARCHAR(100),
        last_value FLOAT,
        last_seen TIMESTAMPTZ,
        notes TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        registered_by INT REFERENCES users(id) ON DELETE SET NULL,
        CONSTRAINT uq_device_sensor UNIQUE(device_id, sensor_name)
    );

    CREATE INDEX IF NOT EXISTS idx_sensors_device_sensor ON sensors(device_id, sensor_name, active);
    CREATE INDEX IF NOT EXISTS idx_sensors_zone ON sensors(device_id, zone_name);

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

    ----------------------------------------------------------------------
    -- AUTHENTICATION & AUTHORIZATION
    ----------------------------------------------------------------------

    -- Create users table
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(100),
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        CONSTRAINT check_role CHECK (role IN ('sys_admin', 'user'))
    );

    -- Create user_site_assignments table (which sites a user can access)
    CREATE TABLE IF NOT EXISTS user_site_assignments (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        site_id INTEGER NOT NULL REFERENCES sites(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, site_id)
    );

    -- Create sessions table for managing user sessions
    CREATE TABLE IF NOT EXISTS sessions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_token VARCHAR(255) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        ip_address VARCHAR(45),
        user_agent TEXT
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_site_assignments_user_id ON user_site_assignments(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_site_assignments_site_id ON user_site_assignments(site_id);

    -- ============================================
    -- API TOKEN AUTHENTICATION
    -- ============================================
    -- IMPORTANT: This must come AFTER devices table is created

    -- Create api_tokens table
    CREATE TABLE IF NOT EXISTS api_tokens (
        id SERIAL PRIMARY KEY,
        token TEXT UNIQUE NOT NULL,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        scopes TEXT[] DEFAULT '{}',  -- Array of permission scopes
        active BOOLEAN DEFAULT TRUE,
        last_used TIMESTAMPTZ,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        created_by INTEGER REFERENCES users(id),
        CONSTRAINT check_owner CHECK (user_id IS NOT NULL OR device_id IS NOT NULL)
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);
    CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id);
    CREATE INDEX IF NOT EXISTS idx_api_tokens_device_id ON api_tokens(device_id);
    CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens(active);

    -- ============================================
    -- PLANT PROFILES - NEW HIERARCHICAL STRUCTURE
    -- ============================================

    -- Plant Types (e.g., Tomato, Lettuce, Carrot)
    CREATE TABLE IF NOT EXISTS plant_types (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        description TEXT,
        emoji VARCHAR(10) DEFAULT '🌱',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );

    -- Plant Varieties (e.g., Tomato - Beefsteak, Tomato - Cherry)
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
        sow_type VARCHAR(20),
        sow_month_start INTEGER,
        sow_month_end INTEGER,
        days_to_germinate INTEGER,
        days_to_transplant_ready INTEGER,
        days_to_harvest INTEGER,
        sow_depth_cm DECIMAL(5, 2),
        spacing_cm DECIMAL(5, 2),
        can_direct_sow BOOLEAN DEFAULT TRUE,
        prefers_transplant BOOLEAN DEFAULT FALSE,
        hardiness_zone VARCHAR(10),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT valid_moisture_range CHECK (moisture_min < moisture_max),
        CONSTRAINT valid_light_range CHECK (light_min IS NULL OR light_max IS NULL OR light_min < light_max),
        CONSTRAINT valid_temp_range CHECK (temp_min IS NULL OR temp_max IS NULL OR temp_min < temp_max),
        UNIQUE(plant_type_id, name)
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS idx_plant_varieties_plant_type_id ON plant_varieties(plant_type_id);
    CREATE INDEX IF NOT EXISTS idx_plant_varieties_name ON plant_varieties(name);

    -- ============================================
    -- PLANT PROFILES DATA SEED
    -- ============================================

    -- Seed plant types (8 types from your existing data)
    INSERT INTO plant_types (id, name, description, emoji, created_at) VALUES
        (1, 'General',     'Safe default for unknown plants',               '🌱', NOW()),
        (2, 'Tomato',      'Tomato plants',                                 '🍅', NOW()),
        (3, 'Lettuce',     'Leafy greens',                                  '🥬', NOW()),
        (4, 'Carrot',      'Root vegetables',                               '🥕', NOW()),
        (5, 'Courgette',   'Summer squash',                                 '🌿', NOW()),
        (6, 'Potato',      'Tuberous vegetables',                           '🥔', NOW()),
        (7, 'Herbs',       'Culinary herbs',                                '🌿', NOW()),
        (8, 'Strawberry',  'Berry plants',                                  '🍓', NOW())
    ON CONFLICT (name) DO NOTHING;

    -- Seed plant varieties (one default per type, using your original constraints)
    INSERT INTO plant_varieties (plant_type_id, name, description, moisture_min, moisture_max, created_at) VALUES
        (1, 'General',      'Safe default for unknown plants',              30, 70, NOW()),
        (2, 'Tomato',       'Consistent moisture, dislikes drying out',     50, 75, NOW()),
        (3, 'Lettuce',      'Likes it consistently moist',                  60, 80, NOW()),
        (4, 'Carrot',       'Dislikes waterlogging',                        35, 60, NOW()),
        (5, 'Courgette',    'Steady moisture during fruiting',              50, 70, NOW()),
        (6, 'Potato',       'Moderate, avoid soggy soil',                   40, 65, NOW()),
        (7, 'Herbs',        'Prefer drier conditions',                      25, 50, NOW()),
        (8, 'Strawberry',   'Even moisture, avoid crown rot',               50, 70, NOW())
    ON CONFLICT (plant_type_id, name) DO NOTHING;

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
        temp_min = 15,
        temp_max = 35
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
        temp_min = 15
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
    -- SENSOR-PLANT ASSIGNMENTS
    -- ============================================

    -- Link a sensor to a plant variety (one variety per moisture sensor)
    CREATE TABLE IF NOT EXISTS sensor_plant_assignments (
        sensor_id INT PRIMARY KEY REFERENCES sensors(id) ON DELETE CASCADE,
        variety_id INT REFERENCES plant_varieties(id) ON DELETE SET NULL,
        assigned_at TIMESTAMPTZ DEFAULT NOW(),
        assigned_by INT REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_sensor_plant_assignments_variety_id ON sensor_plant_assignments(variety_id);

    -- ============================================
    -- MOISTURE EVENTS
    -- ============================================

    -- Moisture event log — every reading evaluated and recorded here
    CREATE TABLE IF NOT EXISTS moisture_events (
        id BIGSERIAL,
        sensor_id INT NOT NULL REFERENCES sensors(id),
        device_id INT NOT NULL REFERENCES devices(id),
        site_id INT NOT NULL REFERENCES sites(id),
        reading NUMERIC(5,2) NOT NULL,
        expected_min NUMERIC(5,2) NOT NULL,
        expected_max NUMERIC(5,2) NOT NULL,
        status VARCHAR(10) NOT NULL CHECK (status IN ('too_dry', 'too_wet', 'ok')),
        action_taken VARCHAR(50),
        last_action_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Create hypertable for TimescaleDB (if available, otherwise just regular table)
    -- Note: This requires TimescaleDB extension
    DO $$
    BEGIN
        IF EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'moisture_events'
        ) AND NOT EXISTS (
            SELECT FROM timescaledb_information.hypertables 
            WHERE hypertable_name = 'moisture_events'
        ) THEN
            SELECT create_hypertable('moisture_events', 'created_at', if_not_exists => TRUE);
        END IF;
    EXCEPTION WHEN OTHERS THEN
        -- TimescaleDB not available, continue with regular table
        NULL;
    END $$;

    CREATE INDEX IF NOT EXISTS idx_moisture_events_sensor ON moisture_events(sensor_id, created_at DESC);

    -- ============================================
    -- UTILITY FUNCTIONS
    -- ============================================

    CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
    RETURNS void AS $$
    BEGIN
        DELETE FROM api_tokens WHERE expires_at < NOW() AND expires_at IS NOT NULL;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
    RETURNS void AS $$
    BEGIN
        DELETE FROM sessions WHERE expires_at < NOW();
    END;
    $$ LANGUAGE plpgsql;

    -- ============================================
    -- DEFAULT DATA
    -- ============================================

    -- Insert default sys_admin user (password: admin123 - CHANGE THIS!)
    -- Password hash is bcrypt hash of 'admin123'
    INSERT INTO users (username, email, password_hash, full_name, role)
    VALUES (
        'admin',
        'admin@smartallotment.local',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMeshmdCKqErG6IvzWP.9zQT5i',
        'System Administrator',
        'sys_admin'
    ) ON CONFLICT (username) DO NOTHING;

    -- Example regular user (password: user123 - CHANGE THIS!)
    INSERT INTO users (username, email, password_hash, full_name, role)
    VALUES (
        'john',
        'john@smartallotment.local',
        '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36sA.Pz0L8xXqEPvEtjN6zu',
        'John Gardener',
        'user'
    ) ON CONFLICT (username) DO NOTHING;

    -- Assign john to site_id 1 (assuming you have sites)
    INSERT INTO user_site_assignments (user_id, site_id)
    SELECT id, 1 FROM users WHERE username = 'john'
    ON CONFLICT (user_id, site_id) DO NOTHING;





    -- ============================================
    -- COMMENTS
    -- ============================================

    COMMENT ON TABLE users IS 'User accounts for dashboard access';
    COMMENT ON TABLE user_site_assignments IS 'Maps users to sites they can access';
    COMMENT ON TABLE sessions IS 'Active user sessions';
    COMMENT ON COLUMN users.role IS 'sys_admin: full access, user: site-restricted access';
    COMMENT ON TABLE api_tokens IS 'API tokens for programmatic access (IoT devices, integrations, etc.)';
    COMMENT ON COLUMN api_tokens.token IS 'The actual API token (hashed in production)';
    COMMENT ON COLUMN api_tokens.user_id IS 'If token belongs to a user (for user API access)';
    COMMENT ON COLUMN api_tokens.device_id IS 'If token belongs to a device (for device data submission)';
    COMMENT ON COLUMN api_tokens.scopes IS 'Array of permission scopes (read:sensors, write:sensors, etc.)';
    COMMENT ON COLUMN api_tokens.name IS 'Human-readable name for the token';
    COMMENT ON TABLE plant_types IS 'Plant categories (Tomato, Lettuce, etc.)';
    COMMENT ON TABLE plant_varieties IS 'Plant varieties with specific constraints (Tomato - Beefsteak, etc.)';
    COMMENT ON TABLE sensor_plant_assignments IS 'Links a moisture sensor to its plant variety';
    COMMENT ON TABLE moisture_events IS 'Log of every moisture evaluation — ok, too_dry, or too_wet';
    COMMENT ON TABLE planted_crops IS 'Garden planting log — records when crops are sown and transplanted';
    COMMENT ON TABLE crop_seasons IS 'Sowing windows for each variety by season';
    COMMENT ON TABLE companion_plants IS 'Beneficial and antagonistic plant relationships';
    COMMENT ON TABLE planting_events IS 'Timeline events for each planted crop (germinated, harvested, etc.)';