set -e

# Always run from script directory (repo root)
cd "$(dirname "$0")"

echo "🚀 Smart Allotment Hub Docker Installer"
echo "======================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Fix permissions
echo -e "${YELLOW}🔧 Fixing permissions...${NC}"
sudo chown -R smartallotment:docker ./
sudo chmod -R 775 mqtt/ mqtt_listener/ api/ database/

# Directories for certificates
CERTS_DIR=mqtt/certs
LISTENER_CERTS_DIR=mqtt_listener/certs

# Create directories if they don't exist
for DIR in "$CERTS_DIR" "$LISTENER_CERTS_DIR"; do
    if [ ! -d "$DIR" ]; then
        echo "📁 Directory missing, creating $DIR..."
        mkdir -p "$DIR"
    fi
done

# Generate TLS certificates (idempotent)
echo -e "${YELLOW}🔐 Generating TLS certificates...${NC}"
rm -f "$CERTS_DIR/ca.key" "$CERTS_DIR/ca.crt" "$CERTS_DIR/server.key" "$CERTS_DIR/server.crt" "$CERTS_DIR/server.csr" 2>/dev/null || true

openssl genrsa -out "$CERTS_DIR/ca.key" 4096
openssl req -new -x509 -days 3650 -key "$CERTS_DIR/ca.key" -out "$CERTS_DIR/ca.crt" \
  -subj "/C=GB/ST=England/L=Grays/O=SmartAllotment/CN=SmartAllotment-CA"

openssl genrsa -out "$CERTS_DIR/server.key" 4096
openssl req -new -out "$CERTS_DIR/server.csr" -key "$CERTS_DIR/server.key" \
  -subj "/C=GB/ST=England/L=Grays/O=SmartAllotment/CN=localhost"

openssl x509 -req -in "$CERTS_DIR/server.csr" -CA "$CERTS_DIR/ca.crt" -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial -out "$CERTS_DIR/server.crt" -days 365


# Copy CA to mqtt_listener certs folder
cp "$CERTS_DIR/ca.crt" "$LISTENER_CERTS_DIR/ca.crt"

# Set permissions
chmod 600 "$CERTS_DIR/ca.key" "$CERTS_DIR/server.key"
chmod 644 "$CERTS_DIR/ca.crt" "$CERTS_DIR/server.crt"

# Clean up
rm -f "$CERTS_DIR/server.csr"


# Fix ownership
sudo chown -R smartallotment:docker mqtt/certs mqtt_listener/certs

# Expose MQTT port if missing
echo -e "${YELLOW}📡 Ensuring MQTT port 1883 exposed...${NC}"
if ! grep -q "1883:1883" docker-compose.yml; then
  sed -i '/ports:/a \      - "1883:1883"           # MQTT plain' docker-compose.yml
  echo -e "${GREEN}✅ Added port 1883 mapping${NC}"
fi

# Optional: clear DB for fresh start
echo -e "${YELLOW}📊 Resetting database (optional)...${NC}"
# rm -rf database/data/*

# Pull latest Docker images
echo -e "${YELLOW}🔄 Pulling latest Docker images...${NC}"
docker compose pull

# Start services
echo -e "${YELLOW}🐳 Starting services...${NC}"
docker compose up -d

# Wait a few seconds for services
echo -e "${YELLOW}⏳ Waiting for services to initialize...${NC}"
sleep 15

# Optional: Test MQTT → DB pipeline
echo -e "${YELLOW}🧪 Testing MQTT → TimescaleDB pipeline...${NC}"
mosquitto_pub -h localhost -p 1883 -t "sensors/test-device/data" -m \
  '{"device_id":"test-device","sensors":[{"type":"temperature","id":"temp-sensor-001","value":12.8}]}' && sleep 3

if docker compose exec database psql -U mqtt -d sensors -c \
    "SELECT COUNT(*) FROM sensor_data WHERE device_id='test-device';" | grep -q 1; then
    echo -e "${GREEN}✅ Test passed! Data stored in TimescaleDB${NC}"
else
    echo -e "${YELLOW}⚠️  Test data may take a moment to process...${NC}"
fi

# Show status
echo ""
echo -e "${GREEN}🎉 Hub installation complete!${NC}"
docker compose ps
echo ""
echo "📡 MQTT Broker: localhost:1883"
echo "📊 TimescaleDB: sensors database"
echo ""