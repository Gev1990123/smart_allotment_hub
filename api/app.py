from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import mqtt_publisher

from routers import auth, users, tokens, devices, sensors, sites, plant_profiles, predictions, ui

app = FastAPI(docs_url=None, redoc_url=None, title="Smart Allotment API")

# Allow all origins for now — tighten this down in production
# to only allow the frontend's actual domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (CSS, JS) and HTML templates from fixed container paths
app.mount("/static", StaticFiles(directory="/api/static"), name="static")

# -------------------------
# Startup
# -------------------------

@app.on_event("startup")
async def startup():
    # Connect the persistent MQTT publisher once when the API boots,
    # so all endpoints can publish without creating a new connection each time
    mqtt_publisher.connect()

# -------------------------
# Routers
# -------------------------

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tokens.router)
app.include_router(devices.router)
app.include_router(sensors.router)
app.include_router(sites.router)
app.include_router(plant_profiles.router)
app.include_router(predictions.router)
app.include_router(ui.router)