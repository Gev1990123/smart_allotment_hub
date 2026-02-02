## Prerequisites

- Raspberry Pi or Linux machine
- Git installed: sudo apt install git
- Python 3.13+ installed: sudo apt install python3 python3-venv python3-pip
- Docker & Docker Compose installed:

```
sudo apt install docker.io docker-compose
```
```
sudo usermod -aG docker $USER
```

## Hub Installation
### Clone Repository
```
cd /opt
sudo mkdir -p /opt/smart_allotment_hub
sudo chown smartallotment:smartallotment /opt/smart_allotment_hub
cd /opt/smart_allotment_hub
git clone git@github.com:Gev1990123/smart_allotment_hub.git .
```

### Install Script
Run the automated installer:
```
chmod +x install_hub.sh
./install_hub.sh
```
The script will:

- Fix permissions
- Create required directories (mqtt/certs, mqtt_listener/certs)
- Generate TLS certificates for MQTT
- Generate .env file for configuration
- Pull Docker images
- Start Hub services via Docker Compose

### Configure .env
The installer prompts for:
```
MQTT_PORT=xx
MQTT_TLS_PORT=xx
API_PORT=xx
POSTGRES_DB=xx
POSTGRES_USER=xx
POSTGRES_PASSWORD=xx
```
All values are stored in .env for Docker Compose.

### Docker Compose Services
Services included:
- mqtt — MQTT Broker (plain & TLS)
- database — Postgres 16 / TimescaleDB
- mqtt_listener — MQTT → TimescaleDB ingestion
- api — FastAPI backend API

Start manually if needed:
```
docker compose up -d
docker compose ps
```

### Testing
Test MQTT → Database pipeline:
```
mosquitto_pub -h localhost -p 1883 -t "sensors/test-device/data" -m '{"device_id":"test-device","sensors":[{"type":"temperature","id":"temp-sensor-001","value":12.8}]}'
```

Check in database:
```
docker compose exec database psql -U mqtt -d sensors -c "SELECT * FROM sensor_data WHERE device_id='test-device';"
```

### Updating Hub
1. Pull Latest Code
```
cd /opt/smart_allotment_hub
git pull origin main
```

2. Update services:
```
./install_hub.sh
```
