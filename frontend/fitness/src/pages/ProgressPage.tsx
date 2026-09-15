import { useEffect, useMemo, useState } from "react"
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts"
import { Label, PageHeader, EmptyState, ChartTooltip } from "../components/ui"
import { getWorkouts, bestE1RM } from "../lib/api"
import type { Workout } from "../lib/api"

const PALETTE = ["#ff4d5e", "#4d9eff", "#ff8c42", "#00e5a0", "#c084fc", "#f5d90a"]

function weekStart(iso: string): string {
  const d = new Date(iso + "T00:00:00")
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7)) // back to Monday
  // Local date fields, not toISOString() (which is UTC and shifts the date
  // backward a day for any positive UTC offset) — see lib/api.ts's todayISO.
  const y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, "0"), day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

export function ProgressPage() {
  const [workouts, setWorkouts] = useState<Workout[]>([])
  const [loading, setLoading] = useState(true)
  const [lift, setLift] = useState<string | null>(null)
  const [view, setView] = useState<"strength" | "volume">("strength")

  useEffect(() => {
    getWorkouts()
      .then(rows => {
        setWorkouts(rows)
        if (rows.length) {
          // Default to the most frequently trained lift — more useful than newest
          const counts = new Map<string, number>()
          rows.forEach(w => counts.set(w.exercise, (counts.get(w.exercise) ?? 0) + 1))
          setLift([...counts.entries()].sort((a, b) => b[1] - a[1])[0][0])
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Exercises ranked by how often they appear, so the selector shows real staples first
  const exercises = useMemo(() => {
    const counts = new Map<string, number>()
    workouts.forEach(w => counts.set(w.exercise, (counts.get(w.exercise) ?? 0) + 1))
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name)
  }, [workouts])

  const colorFor = (name: string) => PALETTE[exercises.indexOf(name) % PALETTE.length]

  const history = useMemo(() => {
    if (!lift) return []
    return workouts
      .filter(w => w.exercise === lift)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map(w => ({ date: w.date.slice(5), e1rm: Math.round(bestE1RM(w)) }))
  }, [lift, workouts])

  const cur = history.at(-1)?.e1rm ?? 0
  const prev = history.length > 1 ? history.at(-2)!.e1rm : cur
  const delta = cur - prev
  const best = history.length ? Math.max(...history.map(d => d.e1rm)) : 0

  const volumeByWeek = useMemo(() => {
    const map = new Map<string, number>()
    workouts.forEach(w => {
      const k = weekStart(w.date)
      map.set(k, (map.get(k) ?? 0) + w.sets.length)
    })
    return [...map.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-10)
      .map(([week, sets]) => ({ week: week.slice(5), sets }))
  }, [workouts])

  const topLifts = exercises.slice(0, 6)

  if (loading) return <EmptyState>Loading…</EmptyState>
  if (!workouts.length) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow="Analytics" title="Progress" />
        <EmptyState>No workout history yet — sync your Garmin sessions to see strength trends.</EmptyState>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Analytics" title="Progress">
        <div className="flex p-1 gap-1 rounded-xl" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)" }}>
          {(["strength", "volume"] as const).map(v => (
            <button key={v} onClick={() => setView(v)}
              className="px-5 py-1.5 rounded-lg font-600 text-sm capitalize transition-all"
              style={{
                fontFamily: "var(--font-display)",
                background: view === v ? "rgba(255,77,94,0.15)" : "transparent",
                color: view === v ? "var(--red)" : "var(--text-muted)",
                border: view === v ? "1px solid rgba(255,77,94,0.25)" : "1px solid transparent",
              }}>
              {v}
            </button>
          ))}
        </div>
      </PageHeader>

      {view === "strength" && (
        <>
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(4, topLifts.length)}, 1fr)` }}>
            {topLifts.slice(0, 4).map(name => {
              const d = workouts.filter(w => w.exercise === name).sort((a, b) => a.date.localeCompare(b.date))
              const v = Math.round(bestE1RM(d.at(-1)!))
              const pr = Math.round(Math.max(...d.map(bestE1RM)))
              const d2 = d.length > 1 ? v - Math.round(bestE1RM(d.at(-2)!)) : 0
              const c = colorFor(name)
              return (
                <button key={name} onClick={() => setLift(name)}
                  className="glass p-4 text-left transition-all"
                  style={{ borderColor: lift === name ? c + "40" : "var(--border)", boxShadow: lift === name ? `0 0 24px ${c}18` : "none" }}>
                  <p className="font-700 text-xs uppercase tracking-wide mb-2 truncate"
                    style={{ color: c, fontFamily: "var(--font-display)" }}>{name}</p>
                  <p className="font-mono font-700" style={{ fontSize: "1.8rem", lineHeight: 1, color: lift === name ? c : "var(--text)", fontFamily: "var(--font-mono)" }}>
                    {v}<span className="text-sm opacity-40 ml-1">lb</span>
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>PR {pr}</span>
                    <span className="font-mono text-[11px]" style={{ color: d2 >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
                      {d2 >= 0 ? "+" : ""}{d2}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>

          <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 300px" }}>
            <div className="glass p-5">
              <div className="flex items-end justify-between mb-5">
                <div>
                  <Label>{lift} — Estimated 1RM</Label>
                  <span className="font-mono font-700 mt-2 block"
                    style={{ fontSize: "3.2rem", lineHeight: 1, color: lift ? colorFor(lift) : "var(--red)", fontFamily: "var(--font-mono)", filter: `drop-shadow(0 0 20px ${lift ? colorFor(lift) : "var(--red)"})` }}>
                    {cur}<span className="text-2xl opacity-40 ml-1">lb</span>
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-mono text-xl font-700" style={{ color: delta >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
                    {delta >= 0 ? "+" : ""}{delta} lb
                  </span>
                  <p className="text-[10px] mt-0.5" style={{ color: "var(--text-dim)" }}>vs previous session</p>
                  <p className="font-mono text-xs mt-2" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>All-time PR: {best} lb</p>
                </div>
              </div>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history}>
                    <defs>
                      <linearGradient id="liftGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={lift ? colorFor(lift) : "#ff4d5e"} stopOpacity={0.2} />
                        <stop offset="100%" stopColor={lift ? colorFor(lift) : "#ff4d5e"} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                    <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} width={36} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="e1rm" name="e1RM" stroke={lift ? colorFor(lift) : "#ff4d5e"} strokeWidth={2.5} fill="url(#liftGrad)" dot={{ r: 3 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass overflow-hidden" style={{ maxHeight: 420 }}>
              <div className="px-4 pt-4 pb-3 border-b" style={{ borderColor: "var(--border)" }}><Label>All Lifts vs PR</Label></div>
              <div className="overflow-y-auto" style={{ maxHeight: 360 }}>
                {exercises.map(name => {
                  const d = workouts.filter(w => w.exercise === name)
                  const b = Math.max(...d.map(bestE1RM))
                  const v = Math.round(bestE1RM(d.sort((x, y) => x.date.localeCompare(y.date)).at(-1)!))
                  const c = colorFor(name)
                  return (
                    <button key={name} onClick={() => setLift(name)} className="w-full px-4 py-3 flex items-center gap-3 transition-all"
                      style={{ borderBottom: "1px solid var(--border)", background: lift === name ? `${c}12` : "transparent" }}>
                      <div className="w-24 shrink-0 text-left">
                        <p className="font-600 text-[11px] uppercase tracking-wide truncate" style={{ color: c, fontFamily: "var(--font-display)" }}>{name}</p>
                      </div>
                      <div className="flex-1">
                        <div className="h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                          <div className="h-full rounded-full" style={{ width: `${(v / b) * 100}%`, background: c, boxShadow: `0 0 6px ${c}` }} />
                        </div>
                      </div>
                      <p className="font-mono text-sm font-600 w-14 text-right" style={{ fontFamily: "var(--font-mono)" }}>
                        {v}<span className="text-[10px] opacity-50">lb</span>
                      </p>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </>
      )}

      {view === "volume" && (
        <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="glass p-5">
            <Label>Sets per Week</Label>
            <div className="h-64 mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={volumeByWeek} barCategoryGap="22%">
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="week" tick={{ fontSize: 11, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} width={28} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="sets" fill="#ff4d5e" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="glass p-5">
            <Label>e1RM Trajectory — Top Lifts</Label>
            <div className="h-64 mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart>
                  <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" type="category" allowDuplicatedCategory={false}
                    tick={{ fontSize: 9, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 9, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} width={36} />
                  <Tooltip content={<ChartTooltip />} />
                  {topLifts.map(name => {
                    const d = workouts.filter(w => w.exercise === name)
                      .sort((a, b) => a.date.localeCompare(b.date))
                      .map(w => ({ date: w.date.slice(5), e1rm: Math.round(bestE1RM(w)) }))
                    return <Line key={name} data={d} type="monotone" dataKey="e1rm" name={name}
                      stroke={colorFor(name)} strokeWidth={1.5} dot={false} />
                  })}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
              {topLifts.map(name => (
                <div key={name} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-sm" style={{ background: colorFor(name) }} />
                  <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
