import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .config import allowed_origins_list, insecure_configuration_warnings
from .database import Base, engine
from .routers import (
    auth, users, credentials, doors, schedules, alerts, faculties, buildings, password_resets,
    energy, zones, academic, access_windows, anomalies, emergency_overrides, command_center,
    audit_logs, investigations, search, face, occupancy, device_faults, rooms_intel, hvac,
)
from .services import (
    mqtt_service, staleness_watchdog, energy_service, automation_engine, hardware_health_service,
    emergency_override_service, device_monitor_service,
)

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    for _w in insecure_configuration_warnings():
        logging.getLogger("app.config").warning("Configuration: %s", _w)
    mqtt_service.start()
    staleness_watchdog.start()
    energy_service.start()
    automation_engine.start()
    hardware_health_service.start()
    emergency_override_service.start()
    device_monitor_service.start()
    yield
    device_monitor_service.stop()
    emergency_override_service.stop()
    hardware_health_service.stop()
    automation_engine.stop()
    energy_service.stop()
    staleness_watchdog.stop()
    mqtt_service.stop()


app = FastAPI(
    title="Smart Building Access Control API",
    version="0.1.0",
    description="Phase 3 backend — matches the REST API spec in the Phase 1 System Design Document.",
    lifespan=lifespan,
)

# Dev-friendly CORS so the Phase 4 dashboard (a separate origin, e.g.
# localhost:5173) can call this API. Tighten allow_origins to the real
# deployed dashboard URL before going anywhere near production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(credentials.router)
app.include_router(doors.router)
app.include_router(schedules.router)
app.include_router(alerts.router)
app.include_router(faculties.router)
app.include_router(buildings.router)
app.include_router(password_resets.router)
app.include_router(energy.router)
app.include_router(zones.router)
app.include_router(academic.router)
app.include_router(access_windows.router)
app.include_router(anomalies.router)
app.include_router(emergency_overrides.router)
app.include_router(command_center.router)
app.include_router(audit_logs.router)
app.include_router(investigations.router)
app.include_router(search.router)
app.include_router(face.router)
app.include_router(occupancy.router)
app.include_router(device_faults.router)
app.include_router(rooms_intel.router)
app.include_router(hvac.router)

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}
