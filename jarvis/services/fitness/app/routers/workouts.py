from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.get("", response_model=list[schemas.WorkoutOut])
def list_workouts(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Workout)
    if start:
        query = query.filter(models.Workout.date >= start)
    if end:
        query = query.filter(models.Workout.date <= end)
    return query.order_by(models.Workout.date.desc()).all()


@router.post("", response_model=schemas.WorkoutOut, status_code=201)
def create_workout(workout: schemas.WorkoutCreate, db: Session = Depends(get_db)):
    db_workout = models.Workout(
        date=workout.date,
        source=workout.source,
        exercise=workout.exercise,
        sets=[s.model_dump() for s in workout.sets],
    )
    db.add(db_workout)
    db.commit()
    db.refresh(db_workout)
    return db_workout


@router.patch("/{workout_id}", response_model=schemas.WorkoutOut)
def update_workout_sets(workout_id: int, update: schemas.WorkoutSetsUpdate, db: Session = Depends(get_db)):
    db_workout = db.get(models.Workout, workout_id)
    if not db_workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    db_workout.sets = [s.model_dump() for s in update.sets]
    db.commit()
    db.refresh(db_workout)
    return db_workout
