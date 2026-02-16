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
    last_value FLOAT,
    last_seen TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
    CONSTRAINT uq_device_sensor UNIQUE(device_id, sensor_name)
);

CREATE INDEX IF NOT EXISTS idx_sensors_device_sensor ON sensors(device_id, sensor_name, active);

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

-- Function to clean up expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM api_tokens WHERE expires_at < NOW() AND expires_at IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

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

-- Comments
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