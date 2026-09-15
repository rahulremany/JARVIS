from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class WorkoutSet(BaseModel):
    reps: int
    weight: float
    rpe: Optional[float] = None


class WorkoutBase(BaseModel):
    date: date
    source: Literal["manual", "garmin"]
    exercise: str
    sets: list[WorkoutSet]


class WorkoutCreate(WorkoutBase):
    pass


class WorkoutOut(WorkoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class WorkoutSetsUpdate(BaseModel):
    sets: list[WorkoutSet]


class NutritionLogBase(BaseModel):
    datetime: datetime
    food_name: str
    calories: float
    protein: float
    carbs: float
    fat: float
    micronutrients: Optional[dict] = None
    source: Literal["photo", "barcode", "manual", "cronometer"]
    food_items: Optional[list[dict]] = None


class NutritionLogCreate(NutritionLogBase):
    pass


class NutritionLogOut(NutritionLogBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DailyTargetBase(BaseModel):
    date: date
    calories: float
    protein: float
    carbs: float
    fat: float


class DailyTargetUpsert(DailyTargetBase):
    pass


class DailyTargetOut(DailyTargetBase):
    model_config = ConfigDict(from_attributes=True)


class GarminRecoveryBase(BaseModel):
    date: date
    hrv: Optional[float] = None
    sleep_score: Optional[float] = None
    stress_score: Optional[float] = None
    resting_hr: Optional[float] = None


class GarminRecoveryUpsert(GarminRecoveryBase):
    pass


class GarminRecoveryOut(GarminRecoveryBase):
    model_config = ConfigDict(from_attributes=True)


class CoachFlag(BaseModel):
    issue: str
    evidence: str
    severity: Literal["low", "medium", "high"]


class CoachNoteBase(BaseModel):
    date: date
    recommendation: str
    reasoning: str
    flags: list[CoachFlag]


class CoachNoteCreate(CoachNoteBase):
    pass


class CoachNoteOut(CoachNoteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SuggestedExercise(BaseModel):
    exercise: str
    sets: int
    reps: str  # e.g. "5" or "8-10"
    target_weight: Optional[float] = None
    notes: Optional[str] = None


class WorkoutRecommendation(BaseModel):
    summary: str
    reasoning: str
    exercises: list[SuggestedExercise]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


class GarminWorkoutExercise(BaseModel):
    exercise: str
    sets: int = 3
    reps: int = 8
    weight_lb: Optional[float] = None
    rest_seconds: Optional[int] = None


class SaveWorkoutRequest(BaseModel):
    name: Optional[str] = None
    exercises: list[GarminWorkoutExercise]


class SaveWorkoutResponse(BaseModel):
    workout_id: Optional[int] = None
    workout_name: str
    uploaded: list[dict]
    skipped: list[str]
    sent_to_device: Optional[str] = None
    device_error: Optional[str] = None


class SavedWorkoutRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    workout_id: Optional[int] = None
    workout_name: str
    exercises: list[dict]
    skipped: list[str]
    auto: int
    created_at: datetime


class MemoryFact(BaseModel):
    index: int
    date: str
    text: str
