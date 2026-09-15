import { useEffect, useMemo, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Label, PageHeader, ChartTooltip } from "../components/ui"
import {
  getNutritionLogs, getLatestTarget, upsertDailyTarget,
  isNotFound, todayISO, daysAgoISO,
} from "../lib/api"
import type { NutritionLog, DailyTarget } from "../lib/api"

export function NutritionPage() {
  const [logs, setLogs] = useState<NutritionLog[]>([])
  const [target, setTarget] = useState<DailyTarget | null>(null)
  const [targetOpen, setTargetOpen] = useState(false)

  const refetch = () => {
    getNutritionLogs().then(setLogs).catch(console.error)
    getLatestTarget().then(setTarget).catch(err => { if (!isNotFound(err)) console.error(err) })
  }
  useEffect(refetch, [])

  const today = todayISO()
  const todayLogs = useMemo(
    () => logs.filter(l => l.datetime.slice(0, 10) === today).sort((a, b) => a.datetime.localeCompare(b.datetime)),
    [logs, today]
  )

  const totals = todayLogs.reduce(
    (a, l) => ({
      calories: a.calories + l.calories, protein: a.protein + l.protein,
      carbs: a.carbs + l.carbs, fat: a.fat + l.fat,
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 }
  )

  // Raw list for display. Cronometer only gives macros as one daily total, so
  // its row is expanded into the actual foods (name/amount/time, no macros —
  // Cronometer doesn't expose per-food macros) rather than shown as a single
  // placeholder line. Everything else keeps its own logged macros.
  const foodRows = useMemo(() => {
    type Row = {
      key: string; time: string; name: string; source: NutritionLog["source"]
      calories: number | null; amount?: string
      macros: { protein: number; carbs: number; fat: number } | null
    }
    const rows: Row[] = []
    for (const log of todayLogs) {
      if (log.source === "cronometer" && log.food_items?.length) {
        for (const [i, item] of log.food_items.entries()) {
          rows.push({
            key: `${log.id}-${i}`, time: item.time || "", name: item.name,
            source: "cronometer", calories: null, amount: item.amount, macros: null,
          })
        }
      } else {
        rows.push({
          key: String(log.id),
          time: new Date(log.datetime).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
          name: log.food_name, source: log.source, calories: log.calories,
          macros: { protein: log.protein, carbs: log.carbs, fat: log.fat },
        })
      }
    }
    return rows
  }, [todayLogs])

  // Last 7 days of intake
  const weekData = Array.from({ length: 7 }).map((_, i) => {
    const iso = daysAgoISO(6 - i)
    const kcal = logs.filter(l => l.datetime.slice(0, 10) === iso).reduce((a, l) => a + l.calories, 0)
    return { day: new Date(iso + "T00:00:00").toLocaleDateString("en-US", { weekday: "short" }), in: Math.round(kcal) }
  })

  const macroCards = [
    { label: "Protein", v: totals.protein, t: target?.protein, color: "var(--red)" },
    { label: "Carbs", v: totals.carbs, t: target?.carbs, color: "var(--orange)" },
    { label: "Fat", v: totals.fat, t: target?.fat, color: "var(--blue)" },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
        title="Nutrition">
        <button onClick={() => setTargetOpen(true)}
          className="px-4 py-2 rounded-xl font-600 text-sm"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
          {target ? "Edit Targets" : "Set Targets"}
        </button>
      </PageHeader>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="glass p-4">
          <Label>Calories Today</Label>
          <p className="font-mono font-700 mt-2" style={{ fontSize: "2.2rem", lineHeight: 1, fontFamily: "var(--font-mono)" }}>
            {Math.round(totals.calories).toLocaleString()}<span className="text-sm opacity-40 ml-1">kcal</span>
          </p>
          <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
            <div className="h-full rounded-full"
              style={{
                width: `${target ? Math.min(100, (totals.calories / target.calories) * 100) : 0}%`,
                background: "linear-gradient(90deg, #ff4d5e, #ff8c42)",
              }} />
          </div>
          <p className="text-[10px] mt-1.5" style={{ color: "var(--orange)" }}>
            {target ? `${Math.round(target.calories - totals.calories).toLocaleString()} kcal remaining` : "no target set"}
          </p>
        </div>
        {macroCards.map(m => (
          <div key={m.label} className="glass p-4">
            <Label>{m.label}</Label>
            <p className="font-mono font-700 mt-2" style={{ fontSize: "2rem", lineHeight: 1, color: m.color, fontFamily: "var(--font-mono)" }}>
              {Math.round(m.v)}<span className="text-sm opacity-40 ml-0.5">g</span>
            </p>
            <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
              <div className="h-full rounded-full"
                style={{ width: `${m.t ? Math.min(100, (m.v / m.t) * 100) : 0}%`, background: m.color, boxShadow: `0 0 8px ${m.color}80` }} />
            </div>
            <p className="font-mono text-[10px] mt-1.5" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              {m.t ? `target ${Math.round(m.t)}g` : "—"}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1fr 1.2fr" }}>
        <div className="glass p-5">
          <Label>Last 7 Days — Calories</Label>
          <div className="h-56 mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={weekData}>
                <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "rgba(240,241,255,0.3)", fontFamily: "var(--font-mono)" }} axisLine={false} tickLine={false} width={42} />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="in" name="Consumed" stroke="var(--orange)" strokeWidth={2.5} dot={{ fill: "var(--orange)", r: 3, strokeWidth: 0 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass overflow-hidden">
          <div className="px-5 pt-4 pb-3 border-b" style={{ borderColor: "var(--border)" }}>
            <Label>Today's Food</Label>
          </div>
          {foodRows.length === 0 ? (
            <p className="px-5 py-8 text-sm text-center" style={{ color: "var(--text-muted)" }}>Nothing logged today yet.</p>
          ) : (
            <div className="overflow-y-auto" style={{ maxHeight: 300 }}>
              {foodRows.map(row => (
                <div key={row.key} className="px-5 py-3.5 flex items-center gap-4" style={{ borderBottom: "1px solid var(--border)" }}>
                  <span className="font-mono text-[10px] w-12 shrink-0" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                    {row.time}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-500 truncate">{row.name}</p>
                    <div className="flex gap-3 mt-0.5">
                      {row.macros ? (
                        <>
                          <span className="font-mono text-[10px]" style={{ color: "var(--red)", fontFamily: "var(--font-mono)" }}>{Math.round(row.macros.protein)}P</span>
                          <span className="font-mono text-[10px]" style={{ color: "var(--orange)", fontFamily: "var(--font-mono)" }}>{Math.round(row.macros.carbs)}C</span>
                          <span className="font-mono text-[10px]" style={{ color: "var(--blue)", fontFamily: "var(--font-mono)" }}>{Math.round(row.macros.fat)}F</span>
                        </>
                      ) : (
                        row.amount && <span className="font-mono text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>{row.amount}</span>
                      )}
                      <span className="font-mono text-[9px]" style={{ color: "var(--text-dim)" }}>
                        {row.source === "cronometer" ? "⬡ Cronometer" : row.source === "barcode" ? "▤ Barcode" : "✎ Manual"}
                      </span>
                    </div>
                  </div>
                  {row.calories != null && (
                    <span className="font-mono text-sm font-600 shrink-0" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                      {Math.round(row.calories)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Daily target modal ── */}
      {targetOpen && (
        <TargetModal current={target} onClose={() => setTargetOpen(false)} onSaved={() => { setTargetOpen(false); refetch() }} />
      )}
    </div>
  )
}

function TargetModal({ current, onClose, onSaved }: {
  current: DailyTarget | null; onClose: () => void; onSaved: () => void
}) {
  const [form, setForm] = useState({
    calories: String(current?.calories ?? 3000),
    protein: String(current?.protein ?? 200),
    carbs: String(current?.carbs ?? 350),
    fat: String(current?.fat ?? 80),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await upsertDailyTarget({
        date: todayISO(),
        calories: Number(form.calories) || 0,
        protein: Number(form.protein) || 0,
        carbs: Number(form.carbs) || 0,
        fat: Number(form.fat) || 0,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save targets")
    } finally {
      setSaving(false)
    }
  }

  const fields: { key: keyof typeof form; label: string; unit: string }[] = [
    { key: "calories", label: "Calories", unit: "kcal" },
    { key: "protein", label: "Protein", unit: "g" },
    { key: "carbs", label: "Carbs", unit: "g" },
    { key: "fat", label: "Fat", unit: "g" },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(8,9,14,0.85)", backdropFilter: "blur(16px)" }}
      onClick={onClose}>
      <div className="glass w-full max-w-sm p-6 mx-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-700 text-xl" style={{ fontFamily: "var(--font-display)" }}>Daily Targets</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-full flex items-center justify-center text-sm"
            style={{ background: "rgba(255,255,255,0.06)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>✕</button>
        </div>
        <div className="space-y-4">
          {fields.map(f => (
            <div key={f.key}>
              <label className="text-[11px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{f.label}</label>
              <div className="flex items-center gap-2 mt-1">
                <input type="number" value={form[f.key]}
                  onChange={e => setForm(prev => ({ ...prev, [f.key]: e.target.value }))}
                  className="flex-1 bg-transparent text-lg font-mono outline-none py-1"
                  style={{ color: "var(--text)", borderBottom: "1px solid var(--border)", fontFamily: "var(--font-mono)" }} />
                <span className="text-xs opacity-50">{f.unit}</span>
              </div>
            </div>
          ))}
        </div>
        {error && <p className="text-xs mt-3" style={{ color: "var(--red)" }}>{error}</p>}
        <button onClick={save} disabled={saving}
          className="w-full mt-6 py-3 rounded-xl font-700 text-sm transition-all"
          style={{
            background: "linear-gradient(135deg, #ff4d5e, #ff8c42)", color: "#fff",
            fontFamily: "var(--font-display)", opacity: saving ? 0.6 : 1,
          }}>
          {saving ? "Saving…" : "Save Targets"}
        </button>
      </div>
    </div>
  )
}
