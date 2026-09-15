import { useEffect, useMemo, useState } from "react"
import { Label, SourceBadge, PageHeader, EmptyState } from "../components/ui"
import { getWorkouts, epley1RM, bestE1RM } from "../lib/api"
import type { Workout } from "../lib/api"

/** Groups workout rows into sessions by date (that's how Garmin records them). */
function groupByDate(workouts: Workout[]): { date: string; exercises: Workout[] }[] {
  const map = new Map<string, Workout[]>()
  for (const w of workouts) {
    if (!map.has(w.date)) map.set(w.date, [])
    map.get(w.date)!.push(w)
  }
  return [...map.entries()]
    .map(([date, exercises]) => ({ date, exercises }))
    .sort((a, b) => b.date.localeCompare(a.date))
}

export function TrainPage() {
  const [workouts, setWorkouts] = useState<Workout[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [selectedExercise, setSelectedExercise] = useState(0)

  useEffect(() => {
    getWorkouts()
      .then(rows => {
        setWorkouts(rows)
        const sessions = groupByDate(rows)
        if (sessions.length > 0) setSelectedDate(sessions[0].date)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const sessions = useMemo(() => groupByDate(workouts), [workouts])
  const session = sessions.find(s => s.date === selectedDate) ?? null
  const exercise = session?.exercises[selectedExercise] ?? null

  // Previous time this exercise was performed, for a real progression comparison
  const previous = useMemo(() => {
    if (!exercise || !session) return null
    return workouts
      .filter(w => w.exercise === exercise.exercise && w.date < session.date)
      .sort((a, b) => b.date.localeCompare(a.date))[0] ?? null
  }, [exercise, session, workouts])

  if (loading) return <EmptyState>Loading sessions…</EmptyState>

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow="Sessions" title="Train" />
        <EmptyState>
          No workouts yet. Sessions sync automatically from your Garmin watch —
          run <span className="font-mono" style={{ color: "var(--blue)" }}>python -m app.garmin_sync</span> or wait for the next auto-sync.
        </EmptyState>
      </div>
    )
  }

  const totalSets = session?.exercises.reduce((a, e) => a + e.sets.length, 0) ?? 0
  const tonnage = session?.exercises.reduce(
    (a, e) => a + e.sets.reduce((s, set) => s + set.weight * set.reps, 0), 0
  ) ?? 0

  return (
    <div className="flex flex-col gap-6" style={{ minHeight: "100%" }}>
      <PageHeader
        eyebrow={session ? new Date(session.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }) : "Sessions"}
        title="Train">
        <SourceBadge source="garmin" />
      </PageHeader>

      <div className="grid gap-4 flex-1" style={{ gridTemplateColumns: "260px 280px 1fr" }}>
        {/* Session list */}
        <div className="glass overflow-hidden flex flex-col" style={{ maxHeight: 620 }}>
          <div className="px-4 pt-4 pb-3 border-b shrink-0" style={{ borderColor: "var(--border)" }}>
            <Label>Sessions</Label>
          </div>
          <div className="overflow-y-auto">
            {sessions.map(s => {
              const active = s.date === selectedDate
              const sets = s.exercises.reduce((a, e) => a + e.sets.length, 0)
              return (
                <button key={s.date}
                  onClick={() => { setSelectedDate(s.date); setSelectedExercise(0) }}
                  className="w-full px-4 py-3.5 text-left transition-all"
                  style={{
                    borderBottom: "1px solid var(--border)",
                    background: active ? "rgba(255,77,94,0.06)" : "transparent",
                    borderLeft: active ? "2px solid var(--red)" : "2px solid transparent",
                  }}>
                  <p className="text-sm font-500">
                    {new Date(s.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </p>
                  <p className="font-mono text-[10px] mt-0.5" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                    {s.exercises.length} exercises · {sets} sets
                  </p>
                </button>
              )
            })}
          </div>
        </div>

        {/* Exercises in session */}
        <div className="glass overflow-hidden flex flex-col" style={{ maxHeight: 620 }}>
          <div className="px-4 pt-4 pb-3 border-b shrink-0 flex items-center justify-between" style={{ borderColor: "var(--border)" }}>
            <Label>Exercises</Label>
            <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
              {Math.round(tonnage).toLocaleString()} lb
            </span>
          </div>
          <div className="overflow-y-auto">
            {session?.exercises.map((e, i) => {
              const active = i === selectedExercise
              return (
                <button key={e.id} onClick={() => setSelectedExercise(i)}
                  className="w-full px-4 py-3.5 text-left flex items-center justify-between transition-all"
                  style={{
                    borderBottom: "1px solid var(--border)",
                    background: active ? "rgba(255,77,94,0.06)" : "transparent",
                    borderLeft: active ? "2px solid var(--red)" : "2px solid transparent",
                  }}>
                  <div className="min-w-0 pr-2">
                    <p className="text-sm font-500 truncate">{e.exercise}</p>
                    <p className="font-mono text-[10px] mt-0.5" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                      {e.sets.length} sets
                    </p>
                  </div>
                  <span className="font-mono text-xs shrink-0" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    {Math.round(bestE1RM(e))}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Set detail */}
        <div className="glass overflow-hidden flex flex-col">
          {exercise && (
            <>
              <div className="px-6 pt-5 pb-4 border-b shrink-0" style={{ borderColor: "var(--border)" }}>
                <h2 className="font-700 text-xl" style={{ fontFamily: "var(--font-display)" }}>{exercise.exercise}</h2>
                <p className="font-mono text-xs mt-1" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  Best e1RM: <span style={{ color: "var(--red)" }}>{Math.round(bestE1RM(exercise))} lb</span>
                  {previous && (
                    <>
                      {" · vs "}
                      {new Date(previous.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}:{" "}
                      <span style={{ color: bestE1RM(exercise) >= bestE1RM(previous) ? "var(--green)" : "var(--orange)" }}>
                        {bestE1RM(exercise) >= bestE1RM(previous) ? "+" : ""}
                        {Math.round(bestE1RM(exercise) - bestE1RM(previous))} lb
                      </span>
                    </>
                  )}
                </p>
              </div>

              <div className="px-6 py-2 grid text-[9px] uppercase tracking-wider shrink-0"
                style={{ gridTemplateColumns: "44px 1fr 1fr 80px 80px", color: "var(--text-dim)", borderBottom: "1px solid var(--border)" }}>
                <span>Set</span><span>Weight</span><span>Reps</span><span>RPE</span><span>e1RM</span>
              </div>

              <div className="overflow-y-auto">
                {exercise.sets.map((s, si) => {
                  const rpeColor = (s.rpe ?? 0) >= 9 ? "var(--red)" : (s.rpe ?? 0) >= 8 ? "var(--orange)" : "var(--text-muted)"
                  return (
                    <div key={si} className="px-6 py-4 grid items-center"
                      style={{ gridTemplateColumns: "44px 1fr 1fr 80px 80px", borderBottom: "1px solid var(--border)" }}>
                      <span className="font-mono text-sm font-600" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{si + 1}</span>
                      <span className="font-mono text-lg font-700" style={{ fontFamily: "var(--font-mono)" }}>
                        {s.weight}<span className="text-xs opacity-50 ml-1">lb</span>
                      </span>
                      <span className="font-mono text-lg font-700" style={{ fontFamily: "var(--font-mono)" }}>{s.reps}</span>
                      <span className="font-mono text-sm font-700" style={{ color: rpeColor, fontFamily: "var(--font-mono)" }}>
                        {s.rpe ?? "—"}
                      </span>
                      <span className="font-mono text-sm" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {Math.round(epley1RM(s.weight, s.reps))} lb
                      </span>
                    </div>
                  )
                })}
              </div>

              <div className="px-6 py-3 mt-auto border-t shrink-0" style={{ borderColor: "var(--border)" }}>
                <p className="font-mono text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                  {totalSets} sets this session · logged via {exercise.source}
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
