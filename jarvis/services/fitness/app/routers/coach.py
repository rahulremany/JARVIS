from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/coach-notes", tags=["coach"])


@router.get("", response_model=list[schemas.CoachNoteOut])
def list_coach_notes(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.CoachNote)
    if start:
        query = query.filter(models.CoachNote.date >= start)
    if end:
        query = query.filter(models.CoachNote.date <= end)
    return query.order_by(models.CoachNote.date.desc()).all()


@router.post("", response_model=schemas.CoachNoteOut, status_code=201)
def create_coach_note(note: schemas.CoachNoteCreate, db: Session = Depends(get_db)):
    db_note = models.CoachNote(
        date=note.date,
        recommendation=note.recommendation,
        reasoning=note.reasoning,
        flags=[f.model_dump() for f in note.flags],
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note
