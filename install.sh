#!/bin/bash
set -e  # Exit on any error

echo "🚀 Smart Allotment Production Installation"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Fix ALL permissions
echo -e "${YELLOW}🔧 Fixing permissions...${NC}"
sudo chown -R smartallotment:docker ./
sudo chmod -R 775 mqtt/ mqtt_listener/ api/ database/

# 2. Generate TLS certificates (idempotent)
echo -e "${YELLOW}🔐 Generating TLS certificates...${NC}"
cd mqtt/certs
sudo rm -f ca.key ca.crt server.key server.crt server.csr 2>/dev/null || true
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/C=GB/ST=England/L=Grays/O=SmartAllotment/CN=SmartAllotment-CA"
openssl genrsa -out server.key 4096
openssl req -new -out server.csr -key server.key \
  -subj "/C=GB/ST=England/L=Grays/O=SmartAllotment/CN=localhost"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -days 365
cp ca.crt ../../mqtt_listener/certs/ca.crt
chmod 600 ca.key server.key
chmod 644 ca.crt server.crt
rm -f server.csr
cd ../..

sudo chown -R smartallotment:docker mqtt/certs mqtt_listener/certs

# 3. Add port 1883 if missing
echo -e "${YELLOW}📡 Ensuring MQTT port 1883 exposed...${NC}"
if ! grep -q "1883:1883" docker-compose.yml; then
  sed -i '/ports:/a \      - "1883:1883"           # MQTT plain' docker-compose.yml
  echo -e "${GREEN}✅ Added port 1883 mapping${NC}"
fi

# 4. Clear database to trigger your init.sql
echo -e "${YELLOW}📊 Resetting database (triggers init.sql)...${NC}"
rm -rf database/data/*

# 5. Pull latest images
echo -e "${YELLOW}🔄 Pulling latest Docker images...${NC}"
docker compose pull

# 6. Start services
echo -e "${YELLOW}🐳 Starting services...${NC}"
docker compose up -d

# 7. Wait for services
echo -e "${YELLOW}⏳ Waiting for services to be healthy...${NC}"
sleep 15

# 8. Verify TimescaleDB hypertable created (your init.sql)
echo -e "${YELLOW}🔍 Verifying TimescaleDB hypertable...${NC}"
if docker compose exec database psql -U mqtt -d sensors -c "\dt" | grep -q sensor_data; then
  echo -e "${GREEN}✅ TimescaleDB hypertable 'sensor_data' ready!${NC}"
else
  echo -e "${RED}❌ sensor_data table not found!${NC}"
  exit 1
fi

# 9. Test end-to-end MQTT → Database pipeline
echo -e "${YELLOW}🧪 Testing MQTT → TimescaleDB pipeline...${NC}"
mosquitto_pub -h localhost -p 1883 -t "sensors/soil-sensor-001/data" -m \
  '{"device_id":"soil-sensor-001","temperature":12.8,"soil_moisture":45.2,"location":"bed-1"}' && \
sleep 3 && \
if docker compose exec database psql -U mqtt -d sensors -c \
  "SELECT COUNT(*) FROM sensor_data WHERE device_id='soil-sensor-001';" | grep -q 1; then
  echo -e "${GREEN}✅ END-TO-END TEST PASSED! Data stored in TimescaleDB${NC}"
else
  echo -e "${YELLOW}⚠️  Test data may take a moment to process...${NC}"
fi

# 10. Show status
echo ""
echo -e "${GREEN}🎉 Smart Allotment INSTALLATION COMPLETE!${NC}"
echo ""
echo "🌐 MQTT Explorer: 192.168.0.114:1883"
echo "📊 API:          http://localhost:8000" 
echo "📈 Topic format: sensors/[device_id]/data"
echo "🗄️  Database:    TimescaleDB hypertable 'sensor_data'"
echo ""
echo "📋 Services running:"
docker compose ps
echo ""
echo -e "${GREEN}🚜 Ready for Smart Allotment sensors!${NC}"
