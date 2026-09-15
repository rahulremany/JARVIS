from fastapi import APIRouter

from .. import garmin_service

router = APIRouter(prefix="/garmin-sync", tags=["sync"])


@router.get("/status")
def sync_status() -> dict:
    """Polled by the UI on launch so it can show progress and refetch when
    data_version changes."""
    return garmin_service.snapshot()


@router.post("/run")
def run_sync(days: int = 7) -> dict:
    """Manual 'refresh now'. If a sync is already in flight this is a no-op
    that just reports the in-flight run."""
    started = garmin_service.start(days=days)
    return {"started": started, **garmin_service.snapshot()}
