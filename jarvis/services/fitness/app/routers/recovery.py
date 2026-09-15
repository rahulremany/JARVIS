from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/garmin-recovery", tags=["recovery"])


@router.get("/latest", response_model=schemas.GarminRecoveryOut)
def get_latest_recovery(db: Session = Depends(get_db)):
    entry = db.query(models.GarminRecovery).order_by(models.GarminRecovery.date.desc()).first()
    if not entry:
        raise HTTPException(status_code=404, detail="No Garmin recovery data synced yet")
    return entry


@router.get("", response_model=list[schemas.GarminRecoveryOut])
def list_recovery(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.GarminRecovery)
    if start:
        query = query.filter(models.GarminRecovery.date >= start)
    if end:
        query = query.filter(models.GarminRecovery.date <= end)
    return query.order_by(models.GarminRecovery.date.desc()).all()


def _upsert_one(db: Session, entry: schemas.GarminRecoveryUpsert) -> models.GarminRecovery:
    db_entry = db.get(models.GarminRecovery, entry.date)
    if db_entry:
        db_entry.hrv = entry.hrv
        db_entry.sleep_score = entry.sleep_score
        db_entry.stress_score = entry.stress_score
        db_entry.resting_hr = entry.resting_hr
    else:
        db_entry = models.GarminRecovery(**entry.model_dump())
        db.add(db_entry)
    return db_entry


@router.put("", response_model=schemas.GarminRecoveryOut)
def upsert_recovery(entry: schemas.GarminRecoveryUpsert, db: Session = Depends(get_db)):
    db_entry = _upsert_one(db, entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry


@router.put("/bulk", response_model=list[schemas.GarminRecoveryOut])
def upsert_recovery_bulk(entries: list[schemas.GarminRecoveryUpsert], db: Session = Depends(get_db)):
    """Used by the Garmin sync/backfill job to write many days at once."""
    db_entries = [_upsert_one(db, entry) for entry in entries]
    db.commit()
    for e in db_entries:
        db.refresh(e)
    return db_entries
