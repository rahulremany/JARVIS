from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/daily-targets", tags=["targets"])


@router.get("/latest", response_model=schemas.DailyTargetOut)
def get_latest_target(db: Session = Depends(get_db)):
    entry = db.query(models.DailyTarget).order_by(models.DailyTarget.date.desc()).first()
    if not entry:
        raise HTTPException(status_code=404, detail="No daily target set yet")
    return entry


@router.put("", response_model=schemas.DailyTargetOut)
def upsert_daily_target(target: schemas.DailyTargetUpsert, db: Session = Depends(get_db)):
    db_entry = db.get(models.DailyTarget, target.date)
    if db_entry:
        db_entry.calories = target.calories
        db_entry.protein = target.protein
        db_entry.carbs = target.carbs
        db_entry.fat = target.fat
    else:
        db_entry = models.DailyTarget(**target.model_dump())
        db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry
