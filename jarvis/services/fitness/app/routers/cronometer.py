from fastapi import APIRouter

from .. import cronometer_sync

router = APIRouter(prefix="/cronometer", tags=["cronometer"])


@router.get("/status")
def status() -> dict:
    """Sync state plus today's remaining budget — polled by the sidebar
    indicator, not by any automatic sync loop (there isn't one)."""
    return {**cronometer_sync.snapshot(), "budget": cronometer_sync.budget_status()}


@router.post("/sync")
def sync_now(days: int = 7) -> dict:
    """The only way a Cronometer sync ever runs — a manual click."""
    started = cronometer_sync.start(days=days)
    return {"started": started, **cronometer_sync.snapshot(), "budget": cronometer_sync.budget_status()}
