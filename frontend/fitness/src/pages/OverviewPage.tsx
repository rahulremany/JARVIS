import { useEffect, useState } from "react"
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer } from "recharts"
import { Label, SourceBadge, RecoveryRing, StatCard, PageHeader } from "../components/ui"
import { SuggestedWorkoutCard } from "../components/SuggestedWorkoutCard"
import {
  getLatestRecovery, getRecovery, getWorkouts, getNutritionLogs, getLatestTarget,
  isNotFound, todayISO, daysAgoISO,
} from "../lib/api"
import type { GarminRecovery, Workout, NutritionLog, DailyTarget } from "../lib/api"

export function OverviewPage() {
  const [recovery, setRecovery] = useState<GarminRecovery | null>(null)
  const [recoveryHistory, setRecoveryHistory] = useState<GarminRecovery[]>([])
  const [recoverySynced, setRecoverySynced] = useState(true)
  const [todayWorkouts, setTodayWorkouts] = useState<Workout[]>([])
  const [weekWorkouts, setWeekWorkouts] = useState<Workout[]>([])
  const [logs, setLogs] = useState<NutritionLog[]>([])
  const [target, setTarget] = useState<DailyTarget | null>(null)

  useEffect(() => {
    getLatestRecovery()
      .then(setRecovery)
      .catch(err => { if (isNotFound(err)) setRecoverySynced(false); else console.error(err) })
    getRecovery({ start: daysAgoISO(13), end: todayISO() }).then(setRecoveryHistory).catch(console.error)

    const today = todayISO()
    getWorkouts({ start: today, end: today }).then(setTodayWorkouts).catch(console.error)
    getNutritionLogs().then(setLogs).catch(console.error)
    getLatestTarget().then(setTarget).catch(err => { if (!isNotFound(err)) console.error(err) })
    getWorkouts({ start: daysAgoISO(6), end: today }).then(setWeekWorkouts).catch(console.error)
  }, [])

  // 7-day volume, oldest → newest
  const volumeByDay = Array.from({ length: 7 }).map((_, i) => {
    const iso = daysAgoISO(6 - i)
    const sets = weekWorkouts.filter(w => w.date === iso).reduce((a, w) => a + w.sets.length, 0)
    return { day: new Date(iso + "T00:00:00").toLocaleDateString("en-US", { weekday: "short" }), sets }
  })
  const totalWeekSets = volumeByDay.reduce((a, d) => a + d.sets, 0)
  const weekTonnage = weekWorkouts.reduce(
    (a, w) => a + w.sets.reduce((s, set) => s + set.weight * set.reps, 0), 0
  )

  // HRV baseline comparison — the kind of context the spec wants surfaced
  const hrvValues = recoveryHistory.map(r => r.hrv).filter((v): v is number => v != null)
  const hrvBaseline = hrvValues.length > 1
    ? hrvValues.reduce((a, v) => a + v, 0) / hrvValues.length
    : null
  const hrvDelta = recovery?.hrv != null && hrvBaseline != null
    ? Math.round(recovery.hrv - hrvBaseline)
    : null

  const readiness = recovery?.sleep_score != null ? Math.round(recovery.sleep_score) : 0

  const today = todayISO()
  const todayLogs = logs.filter(l => l.datetime.slice(0, 10) === today)
  const totals = todayLogs.reduce(
    (a, l) => ({
      calories: a.calories + l.calories, protein: a.protein + l.protein,
      carbs: a.carbs + l.carbs, fat: a.fat + l.fat,
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 }
  )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
        title="Overview">
        <SourceBadge source="garmin" />
        <SourceBadge source="claude" />
      </PageHeader>

      {/* Top stat row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="HRV" value={recovery?.hrv != null ? Math.round(recovery.hrv) : "—"} unit="ms"
          color="var(--green)"
          sub={hrvDelta != null ? `${hrvDelta >= 0 ? "↑ +" : "↓ "}${hrvDelta}ms vs 14-day avg` : "no baseline yet"} />
        <StatCard label="Resting HR" value={recovery?.resting_hr != null ? Math.round(recovery.resting_hr) : "—"} unit="bpm"
          color="var(--blue)" sub={recovery ? `as of ${recovery.date}` : "not synced"} />
        <StatCard label="Sleep Score" value={recovery?.sleep_score != null ? Math.round(recovery.sleep_score) : "—"} unit="/100"
          color="var(--orange)" sub={recovery?.sleep_score != null && recovery.sleep_score < 60 ? "below par" : "on track"} />
        <StatCard label="Stress" value={recovery?.stress_score != null ? Math.round(recovery.stress_score) : "—"}
          color="var(--purple)" sub="Garmin avg for the day" />
      </div>

      {/* Main 3-column grid */}
      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        {/* Readiness */}
        <div className="glass p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <Label>Readiness</Label>
            <SourceBadge source="garmin" />
          </div>
          {!recoverySynced ? (
            <p className="text-xs py-8 text-center" style={{ color: "var(--text-muted)" }}>
              No Garmin data synced yet.
            </p>
          ) : (
            <div className="flex flex-col items-center py-2">
              <RecoveryRing score={readiness} />
              <div className="mt-5 w-full space-y-2">
                {[
                  { k: "Sleep", v: recovery?.sleep_score, color: "var(--green)" },
                  { k: "HRV", v: recovery?.hrv, color: "var(--blue)" },
                  { k: "Stress", v: recovery?.stress_score, color: "var(--orange)" },
                ].map(m => (
                  <div key={m.k} className="flex items-center gap-3">
                    <span className="text-[10px] w-16 shrink-0" style={{ color: "var(--text-muted)" }}>{m.k}</span>
                    <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                      <div className="h-full rounded-full"
                        style={{ width: `${Math.min(100, m.v ?? 0)}%`, background: m.color, boxShadow: `0 0 6px ${m.color}80` }} />
                    </div>
                    <span className="font-mono text-xs w-8 text-right" style={{ color: m.color, fontFamily: "var(--font-mono)" }}>
                      {m.v != null ? Math.round(m.v) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Today's session */}
        <div className="glass p-4 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <Label>Today's Session</Label>
            {todayWorkouts.length > 0 && (
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                style={{ background: "var(--red-dim)", color: "var(--red)", fontFamily: "var(--font-mono)" }}>
                {todayWorkouts.reduce((a, w) => a + w.sets.length, 0)} sets
              </span>
            )}
          </div>
          {todayWorkouts.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Nothing logged yet today. Sessions sync automatically from your watch.
            </p>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
              {todayWorkouts.map((ex, i) => (
                <div key={ex.id} className="flex items-center justify-between py-2"
                  style={{ borderTop: i > 0 ? "1px solid var(--border)" : "none" }}>
                  <p className="text-xs font-500 truncate pr-2">{ex.exercise}</p>
                  <p className="font-mono text-xs shrink-0" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                    {ex.sets.length}×{ex.sets[0]?.reps} @ {ex.sets[0]?.weight}lb
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Nutrition snapshot */}
        <div className="glass p-5 flex flex-col gap-4">
          <Label>Today — Nutrition</Label>
          <div>
            <p className="font-mono font-700" style={{ fontSize: "2.2rem", lineHeight: 1, fontFamily: "var(--font-mono)" }}>
              {Math.round(totals.calories).toLocaleString()}<span className="text-base opacity-40 ml-1">kcal</span>
            </p>
            <p className="text-[11px] mt-1" style={{ color: "var(--orange)" }}>
              {target
                ? `${Math.round(target.calories - totals.calories).toLocaleString()} remaining · target ${Math.round(target.calories).toLocaleString()}`
                : "no daily target set"}
            </p>
          </div>
          <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
            <div className="h-full rounded-full"
              style={{
                width: `${target ? Math.min(100, (totals.calories / target.calories) * 100) : 0}%`,
                background: "linear-gradient(90deg, #ff4d5e, #ff8c42)",
              }} />
          </div>
          <div className="space-y-2.5 mt-1">
            {[
              { label: "Protein", v: totals.protein, t: target?.protein, color: "var(--red)" },
              { label: "Carbohydrates", v: totals.carbs, t: target?.carbs, color: "var(--orange)" },
              { label: "Fat", v: totals.fat, t: target?.fat, color: "var(--blue)" },
            ].map(m => (
              <div key={m.label}>
                <div className="flex justify-between mb-1">
                  <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{m.label}</span>
                  <span className="font-mono text-[10px]" style={{ color: m.color, fontFamily: "var(--font-mono)" }}>
                    {Math.round(m.v)}g{m.t ? ` / ${Math.round(m.t)}g` : ""}
                  </span>
                </div>
                <div className="h-1 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                  <div className="h-full rounded-full"
                    style={{ width: `${m.t ? Math.min(100, (m.v / m.t) * 100) : 0}%`, background: m.color }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Claude's suggested workout — real API call */}
      <SuggestedWorkoutCard />

      {/* Volume */}
      <div className="glass p-5">
        <div className="flex items-center justify-between mb-4">
          <Label>This Week — Volume</Label>
          <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
            {totalWeekSets} sets · {Math.round(weekTonnage).toLocaleString()} lb tonnage
          </span>
        </div>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={volumeByDay} barCategoryGap="32%">
              <defs>
                <linearGradient id="volGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4d5e" />
                  <stop offset="100%" stopColor="#ff8c42" stopOpacity={0.5} />
                </linearGradient>
              </defs>
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: "rgba(240,241,255,0.35)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Bar dataKey="sets" fill="url(#volGrad)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
