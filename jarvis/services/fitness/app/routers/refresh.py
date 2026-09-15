from fastapi import APIRouter

from .. import refresh

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.get("/status")
def refresh_status() -> dict:
    """Everything the UI needs to know in one poll: whether a refresh is in
    flight, and the data_version it should refetch on."""
    return refresh.status()


@router.post("")
def run_refresh(force: bool = False) -> dict:
    """Re-check every source. Called on app launch and on every page load."""
    return refresh.refresh_all(force=force)
