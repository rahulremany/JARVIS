import logging
import os
import threading
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from . import garmin_service
from .database import Base, engine
from .routers import coach, cronometer, nutrition, recovery, refresh, sync, targets, workout_coach, workouts

logger = logging.getLogger("volt.autosync")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Volt API", version="0.1.0")

AUTOSYNC_INTERVAL_HOURS = float(os.environ.get("GARMIN_AUTOSYNC_INTERVAL_HOURS", "1"))

# The app is launched on demand, so the launch sync is the one that matters —
# it reaches back far enough to fill any gap since the last time the app was
# opened. The periodic refresh only exists for a session left open for hours.
STARTUP_SYNC_DAYS = int(os.environ.get("GARMIN_STARTUP_SYNC_DAYS", "7"))
REFRESH_SYNC_DAYS = 2


def _autosync_loop():
    garmin_service.start(days=STARTUP_SYNC_DAYS)
    while True:
        time.sleep(AUTOSYNC_INTERVAL_HOURS * 3600)
        # Only the launch sync auto-saves a workout; the hourly refresh just
        # keeps recovery data current.
        garmin_service.start(days=REFRESH_SYNC_DAYS, auto_save=False)


@app.on_event("startup")
def start_autosync():
    threading.Thread(target=_autosync_loop, daemon=True).start()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|10\.0\.0\.108):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workouts.router)
app.include_router(nutrition.router)
app.include_router(targets.router)
app.include_router(recovery.router)
app.include_router(coach.router)
app.include_router(workout_coach.router)
app.include_router(sync.router)
app.include_router(refresh.router)
app.include_router(cronometer.router)


@app.get("/health")
def health():
    return {"status": "ok"}
