----------------------------------------------------------------------
-- Smart Allotment PostgreSQL Schema
-- Long-table format: one sensor per row
----------------------------------------------------------------------

DROP TABLE IF EXISTS pump_events;
DROP TABLE IF EXISTS sensor_data;
DROP TABLE IF EXISTS sites;

----------------------------------------------------------------------
-- Sites
----------------------------------------------------------------------

CREATE TABLE sites (
    id SERIAL PRIMARY KEY,
    site_code VARCHAR(50) UNIQUE NOT NULL,
    friendly_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

----------------------------------------------------------------------
-- Sensor Data (one row per sensor reading)
----------------------------------------------------------------------

CREATE TABLE sensor_data (
    id BIGSERIAL PRIMARY KEY,

    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,

    -- Device identifier (Raspberry Pi, ESP32, etc.)
    device_id VARCHAR(50) NOT NULL,

    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Your requested data structure:
    sensor_name VARCHAR(50) NOT NULL,        -- e.g. "soil_moisture"
    sensor_value DOUBLE PRECISION NOT NULL,  -- e.g. "42.5"
    unit VARCHAR(20),                        -- e.g. "%"

    raw JSONB
);

CREATE INDEX idx_sensor_data_site_time ON sensor_data(site_id, timestamp);
CREATE INDEX idx_sensor_data_device_time ON sensor_data(device_id, timestamp);
CREATE INDEX idx_sensor_name ON sensor_data(sensor_name);

----------------------------------------------------------------------
-- Pump Events
----------------------------------------------------------------------

CREATE TABLE pump_events (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action VARCHAR(10) NOT NULL,
    triggered_by VARCHAR(50)
);

CREATE INDEX idx_pump_events_site_time ON pump_events(site_id, event_time);

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
    site_id INTEGER NOT NULL,
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

-- Clean up expired sessions function
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    DELETE FROM sessions WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE users IS 'User accounts for dashboard access';
COMMENT ON TABLE user_site_assignments IS 'Maps users to sites they can access';
COMMENT ON TABLE sessions IS 'Active user sessions';
COMMENT ON COLUMN users.role IS 'sys_admin: full access, user: site-restricted access';

-- ============================================
-- API TOKEN AUTHENTICATION
-- ============================================

-- Create api_tokens table
CREATE TABLE IF NOT EXISTS api_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(64) UNIQUE NOT NULL,
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

-- Function to clean up expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM api_tokens WHERE expires_at < NOW() AND expires_at IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE api_tokens IS 'API tokens for programmatic access (IoT devices, integrations, etc.)';
COMMENT ON COLUMN api_tokens.token IS 'The actual API token (hashed in production)';
COMMENT ON COLUMN api_tokens.user_id IS 'If token belongs to a user (for user API access)';
COMMENT ON COLUMN api_tokens.device_id IS 'If token belongs to a device (for device data submission)';
COMMENT ON COLUMN api_tokens.scopes IS 'Array of permission scopes (read:sensors, write:sensors, etc.)';
COMMENT ON COLUMN api_tokens.name IS 'Human-readable name for the token';
