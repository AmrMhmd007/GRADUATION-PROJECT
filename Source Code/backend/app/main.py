from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .database import Base, engine
from .routers import auth, users, credentials, doors, schedules, alerts, faculties, buildings
from .services import mqtt_service, staleness_watchdog

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    mqtt_service.start()
    staleness_watchdog.start()
    yield
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
    allow_origins=["*"],
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

app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/health")
def health():
    return {"status": "ok"}
