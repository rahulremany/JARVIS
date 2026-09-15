import { useEffect, useState } from "react"
import { Label, SourceBadge, Spinner } from "./ui"
import { getTodaysWorkoutRecommendation, saveWorkoutToGarmin, getTodaysSavedWorkout, isNotFound } from "../lib/api"
import type { WorkoutRecommendation, SaveWorkoutResult, SavedWorkoutRecord } from "../lib/api"

export function SuggestedWorkoutCard({ onAsk }: { onAsk?: (rec: WorkoutRecommendation) => void }) {
  const [rec, setRec] = useState<WorkoutRecommendation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<SaveWorkoutResult | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [alreadySaved, setAlreadySaved] = useState<SavedWorkoutRecord | null>(null)

  // Whether today's session already went to Garmin — the launch auto-save
  // usually gets there first, so the button shouldn't invite a duplicate.
  useEffect(() => {
    getTodaysSavedWorkout()
      .then(setAlreadySaved)
      .catch(err => { if (!isNotFound(err)) console.error(err) })
  }, [])

  useEffect(() => {
    getTodaysWorkoutRecommendation()
      .then(setRec)
      .catch(err => setError(err instanceof Error ? err.message : "Failed to get a recommendation"))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="glass p-5 flex items-center gap-3">
        <Spinner />
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>Asking Claude for today's workout…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 rounded-2xl text-xs"
        style={{ background: "var(--red-dim)", color: "var(--red)", border: "1px solid rgba(255,77,94,0.2)" }}>
        Couldn't get a recommendation: {error}
      </div>
    )
  }

  if (!rec) return null

  const saveToGarmin = async () => {
    setSaving(true)
    setSaveError(null)
    setSaved(null)
    try {
      const result = await saveWorkoutToGarmin(
        rec.exercises.map(e => ({
          exercise: e.exercise, sets: e.sets, reps: e.reps, weight_lb: e.target_weight,
        })),
        `Volt — ${rec.summary}`.slice(0, 80),
      )
      setSaved(result)
      setAlreadySaved(null)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "unknown error")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="glass overflow-hidden" style={{ borderColor: "rgba(124,95,255,0.2)" }}>
      <button className="w-full px-6 py-4 flex items-center gap-4 text-left" onClick={() => setExpanded(e => !e)}>
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-1">
            <Label>Suggested Workout</Label>
            <SourceBadge source="claude" />
          </div>
          <p className="text-sm font-500" style={{ color: "var(--text)" }}>{rec.summary}</p>
        </div>
        <span className="text-sm transition-transform shrink-0"
          style={{ color: "var(--text-dim)", display: "inline-block", transform: expanded ? "rotate(180deg)" : "none" }}>⌄</span>
      </button>

      {expanded && (
        <>
          <div className="border-t px-6 py-5 grid gap-3" style={{ borderColor: "var(--border)", gridTemplateColumns: "1fr 1fr" }}>
            {rec.exercises.map((ex, i) => (
              <div key={i} className="p-4 rounded-xl"
                style={{ background: "rgba(124,95,255,0.05)", border: "1px solid rgba(124,95,255,0.15)" }}>
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <p className="text-sm font-600">{ex.exercise}</p>
                  <span className="font-mono text-xs shrink-0" style={{ color: "var(--purple)", fontFamily: "var(--font-mono)" }}>
                    {ex.sets} × {ex.reps}{ex.target_weight != null ? ` @ ${ex.target_weight}lb` : ""}
                  </span>
                </div>
                {ex.notes && (
                  <p className="text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>{ex.notes}</p>
                )}
              </div>
            ))}
          </div>
          <div className="px-6 pb-5 border-t" style={{ borderColor: "var(--border)" }}>
            <p className="text-[10px] uppercase tracking-[0.12em] mt-4 mb-1.5" style={{ color: "var(--text-muted)" }}>Reasoning</p>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{rec.reasoning}</p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              {onAsk && (
                <button onClick={() => onAsk(rec)}
                  className="px-4 py-2 rounded-xl font-600 text-sm"
                  style={{
                    background: "linear-gradient(135deg, #7c5fff, #c084fc)",
                    color: "#fff", fontFamily: "var(--font-display)",
                  }}>
                  Ask the coach about this
                </button>
              )}
              <button onClick={saveToGarmin} disabled={saving}
                className="px-4 py-2 rounded-xl font-600 text-sm disabled:opacity-60"
                style={{
                  background: "rgba(255,255,255,0.04)", color: "var(--text)",
                  border: "1px solid var(--border)", fontFamily: "var(--font-display)",
                }}>
                {saving ? "Saving to Garmin…" : alreadySaved ? "Save again" : "Save to Garmin"}
              </button>
            </div>

            {alreadySaved && !saved && (
              <p className="mt-3 text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                {alreadySaved.auto ? "Auto-saved" : "Saved"} to Garmin at{" "}
                {new Date(alreadySaved.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} —{" "}
                <span style={{ color: "var(--text)" }}>{alreadySaved.workout_name}</span>. Sync your watch to see it.
              </p>
            )}
            {saved && (
              <p className="mt-3 text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                Saved <span style={{ color: "var(--text)" }}>{saved.workout_name}</span> to your Garmin
                workouts ({saved.uploaded.length} exercise{saved.uploaded.length === 1 ? "" : "s"}).{" "}
                {saved.sent_to_device
                  ? <>Queued for <span style={{ color: "var(--text)" }}>{saved.sent_to_device}</span> — sync the watch and it'll be in your workout list.</>
                  : <>It's in Garmin Connect, but queueing it for the watch failed ({saved.device_error}), so you may need to hit "Send to Device" there.</>}
                {saved.skipped.length > 0 && (
                  <> Garmin had no match for {saved.skipped.join(", ")}, so {saved.skipped.length === 1 ? "it was" : "they were"} left out.</>
                )}
              </p>
            )}
            {saveError && (
              <p className="mt-3 text-[11px]" style={{ color: "var(--red)" }}>Couldn't save to Garmin: {saveError}</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
