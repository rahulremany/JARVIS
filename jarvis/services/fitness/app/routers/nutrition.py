from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/nutrition-logs", tags=["nutrition"])


@router.get("", response_model=list[schemas.NutritionLogOut])
def list_nutrition_logs(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.NutritionLog)
    if start:
        query = query.filter(models.NutritionLog.datetime >= start)
    if end:
        query = query.filter(models.NutritionLog.datetime <= end)
    return query.order_by(models.NutritionLog.datetime.desc()).all()


@router.post("", response_model=schemas.NutritionLogOut, status_code=201)
def create_nutrition_log(entry: schemas.NutritionLogCreate, db: Session = Depends(get_db)):
    db_entry = models.NutritionLog(**entry.model_dump())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry
