from sqlalchemy import Column, Integer, Float, String, Date, DateTime, JSON

from .database import Base


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    source = Column(String, nullable=False)  # "manual" | "garmin"
    exercise = Column(String, nullable=False)
    sets = Column(JSON, nullable=False)  # list of {reps, weight, rpe}


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    datetime = Column(DateTime, nullable=False, index=True)
    food_name = Column(String, nullable=False)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)
    micronutrients = Column(JSON, nullable=True)
    source = Column(String, nullable=False)  # "photo" | "barcode" | "manual" | "cronometer"
    # For source="cronometer": the actual foods logged that day (name/amount/
    # time from Cronometer's servings export), since Cronometer only gives us
    # macros as a daily total, not per food — this is what lets the UI show a
    # real food list instead of one "Cronometer — <date>" placeholder row.
    food_items = Column(JSON, nullable=True)


class DailyTarget(Base):
    __tablename__ = "daily_targets"

    date = Column(Date, primary_key=True)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)


class CronometerSyncBudget(Base):
    """Tracks how many manual Cronometer syncs have been spent today. Cronometer
    rate-limits its export endpoints (~10 exports/day observed; each sync here
    spends 2 — daily_summary + servings), and this app is launched on demand,
    so an in-memory counter would reset every relaunch and silently blow the
    budget. Persisted so the count survives restarts within the same day."""
    __tablename__ = "cronometer_sync_budget"

    date = Column(Date, primary_key=True)
    count = Column(Integer, nullable=False, default=0)


class GarminRecovery(Base):
    __tablename__ = "garmin_recovery"

    date = Column(Date, primary_key=True)
    hrv = Column(Float, nullable=True)
    sleep_score = Column(Float, nullable=True)
    stress_score = Column(Float, nullable=True)
    resting_hr = Column(Float, nullable=True)


class CoachNote(Base):
    __tablename__ = "coach_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    recommendation = Column(String, nullable=False)
    reasoning = Column(String, nullable=False)
    flags = Column(JSON, nullable=False)  # list of {issue, evidence, severity}


class GarminSavedWorkout(Base):
    """One row per day a workout was uploaded to the Garmin workout library.
    Keyed by date so the auto-save at launch is idempotent — reopening the app
    five times a day doesn't leave five copies in Garmin."""
    __tablename__ = "garmin_saved_workouts"

    date = Column(Date, primary_key=True)
    workout_id = Column(Integer, nullable=True)
    workout_name = Column(String, nullable=False)
    exercises = Column(JSON, nullable=False)  # list of {requested, matched}
    skipped = Column(JSON, nullable=False)  # exercise names Garmin had no match for
    auto = Column(Integer, nullable=False, default=0)  # 1 = saved automatically at launch
    created_at = Column(DateTime, nullable=False)


