import { useEffect, useState } from "react"
import { OverviewPage } from "./pages/OverviewPage"
import { TrainPage } from "./pages/TrainPage"
import { ProgressPage } from "./pages/ProgressPage"
import { NutritionPage } from "./pages/NutritionPage"
import { CoachPage } from "./pages/CoachPage"
import {
  getLatestRecovery, getRecovery, getRefreshStatus, runRefresh, isNotFound,
  getCronometerStatus, syncCronometer,
} from "./lib/api"
import type { RefreshStatus, CronometerStatus } from "./lib/api"

const navItems = [
  { id: "overview", label: "Overview", icon: "⌂" },
  { id: "train", label: "Train", icon: "◈" },
  { id: "progress", label: "Progress", icon: "↗" },
  { id: "nutrition", label: "Nutrition", icon: "⬡" },
  { id: "coach", label: "Coach", icon: "✦" },
] as const

type PageId = typeof navItems[number]["id"]

/**
 * Drives the "open it and everything is current" behaviour.
 *
 * On mount — which means every page load, not just backend launch — this asks
 * the backend to re-check Garmin, then polls until it settles. Any source
 * that writes new rows bumps `data_version`, and the app remounts its pages
 * on that tick so a freshly synced workout appears without you touching
 * anything.
 */
function useRefresh() {
  const [state, setState] = useState<RefreshStatus | null>(null)
  const [reachable, setReachable] = useState(true)
  const [synced, setSynced] = useState<string | null>(null)

  const busy = state?.busy ?? false
  const dataVersion = state?.data_version ?? 0

  // Ask for fresh data as soon as the app is open.
  useEffect(() => {
    runRefresh().then(setState).catch(() => setReachable(false))
  }, [])

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const s = await getRefreshStatus()
        if (cancelled) return
        setState(s)
        setReachable(true)
      } catch {
        if (!cancelled) setReachable(false)
      }
      if (!cancelled) timer = window.setTimeout(poll, busy ? 1000 : 20000)
    }

    poll()
    return () => { cancelled = true; if (timer) window.clearTimeout(timer) }
  }, [busy])

  // Re-read what actually landed in the DB whenever new data arrives.
  useEffect(() => {
    let cancelled = false
    getLatestRecovery()
      .then(async r => {
        const rows = await getRecovery().catch(() => [])
        if (!cancelled) setSynced(`${r.date} · ${rows.length} days`)
      })
      .catch(err => { if (!isNotFound(err)) console.error(err); if (!cancelled) setSynced(null) })
    return () => { cancelled = true }
  }, [dataVersion])

  const garminStatus = state?.garmin.status
  const detail = !reachable ? "backend unreachable"
    : garminStatus === "running" ? "syncing…"
    : garminStatus === "mfa" ? "needs MFA — run sync in terminal"
    : garminStatus === "error" ? `sync failed — ${state?.garmin.detail ?? "see logs"}`
    : garminStatus === "disabled" ? "credentials not set"
    : synced ?? "no data synced yet"

  const refresh = () => {
    runRefresh().then(setState).catch(() => setReachable(false))
  }

  return {
    garmin: { ok: reachable && synced != null, detail, running: busy },
    dataVersion,
    refresh,
  }
}

/**
 * Cronometer is deliberately NOT part of useRefresh — it never syncs on
 * launch or reload, only when this hook's `sync()` is called from a click.
 * Cronometer rate-limits its export endpoints, so the status poll here only
 * ever reads state (cheap), never triggers a sync on its own.
 */
function useCronometer() {
  const [status, setStatus] = useState<CronometerStatus | null>(null)
  const [syncing, setSyncing] = useState(false)

  const load = () => getCronometerStatus().then(setStatus).catch(() => {})

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 30000)
    return () => window.clearInterval(timer)
  }, [])

  const sync = async () => {
    if (syncing || (status && status.budget.remaining <= 0)) return
    setSyncing(true)
    try {
      const result = await syncCronometer()
      setStatus(result)
    } finally {
      setSyncing(false)
    }
  }

  const remaining = status?.budget.remaining
  const limit = status?.budget.limit
  const detail = !status ? "checking…"
    : syncing || status.status === "checking" ? "syncing…"
    : status.status === "disabled" ? "not configured"
    : status.status === "error" ? status.detail ?? "sync failed"
    : status.detail ?? "never synced"

  return {
    detail,
    ok: status?.status === "ok",
    syncing: syncing || status?.status === "checking",
    remaining, limit,
    canSync: (remaining ?? 1) > 0,
    sync,
  }
}

export default function App() {
  const [page, setPage] = useState<PageId>("overview")
  const { garmin, dataVersion, refresh } = useRefresh()
  const cronometer = useCronometer()

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--bg)" }}>
      <div className="pointer-events-none fixed inset-0 z-0"
        style={{ background: "radial-gradient(ellipse 60% 40% at 30% 0%, rgba(255,77,94,0.07), transparent 60%), radial-gradient(ellipse 40% 30% at 80% 100%, rgba(124,95,255,0.05), transparent 60%)" }} />

      {/* Sidebar */}
      <aside className="relative z-10 flex flex-col shrink-0"
        style={{ width: 220, background: "rgba(8,9,14,0.8)", borderRight: "1px solid var(--border)", backdropFilter: "blur(20px)" }}>
        <div className="px-5 py-6">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{ background: "linear-gradient(135deg, #ff4d5e, #ff8c42)", boxShadow: "0 0 16px rgba(255,77,94,0.4)" }}>
              <span className="text-white font-700 text-xs">V</span>
            </div>
            <div>
              <p className="font-700 text-sm leading-none" style={{ fontFamily: "var(--font-display)" }}>Volt</p>
              <p className="text-[9px] mt-0.5" style={{ color: "var(--text-muted)" }}>Personal Coach</p>
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3 flex-1">
          {navItems.map(item => {
            const active = page === item.id
            return (
              <button key={item.id} onClick={() => setPage(item.id)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-left w-full transition-all"
                style={{
                  background: active ? "rgba(255,77,94,0.1)" : "transparent",
                  color: active ? "var(--red)" : "var(--text-dim)",
                  border: active ? "1px solid rgba(255,77,94,0.2)" : "1px solid transparent",
                }}>
                <span className="text-base leading-none" style={{ filter: active ? "drop-shadow(0 0 6px var(--red))" : "none" }}>{item.icon}</span>
                <span className="font-600 text-sm" style={{ fontFamily: "var(--font-display)" }}>{item.label}</span>
                {active && <div className="ml-auto w-1.5 h-1.5 rounded-full" style={{ background: "var(--red)", boxShadow: "0 0 6px var(--red)" }} />}
              </button>
            )
          })}
        </nav>

        <div className="px-3 pb-5 space-y-2">
          <p className="text-[9px] uppercase tracking-widest px-3 mb-2" style={{ color: "var(--text-dim)" }}>Connected</p>
          {[
            { label: "Garmin Venu X1", color: "var(--blue)", status: garmin.detail, ok: garmin.ok, onClick: refresh, title: "Sync now" },
            { label: "Claude API", color: "var(--purple)", status: "claude-sonnet-5", ok: true, onClick: undefined, title: undefined },
          ].map(c => (
            <button key={c.label} onClick={c.onClick} disabled={!c.onClick} title={c.title}
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg w-full text-left transition-colors disabled:cursor-default"
              style={{ background: "rgba(255,255,255,0.025)", border: "1px solid var(--border)" }}>
              <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.ok || garmin.running ? "breathe" : ""}`}
                style={{ background: c.ok ? c.color : "var(--text-dim)" }} />
              <div className="min-w-0">
                <p className="text-[10px] font-500 truncate">{c.label}</p>
                <p className="text-[9px] truncate" style={{ color: "var(--text-dim)" }}>{c.status}</p>
              </div>
            </button>
          ))}

          {/* Cronometer — manual sync only, so this gets its own button rather
              than the whole row being clickable, plus the daily budget so a
              click doesn't come as a surprise "sync failed" later. */}
          <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg"
            style={{ background: "rgba(255,255,255,0.025)", border: "1px solid var(--border)" }}>
            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${cronometer.ok ? "breathe" : ""}`}
              style={{ background: cronometer.ok ? "var(--green)" : "var(--text-dim)" }} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-1">
                <p className="text-[10px] font-500 truncate">Cronometer</p>
                {cronometer.remaining != null && (
                  <span className="font-mono text-[8px] shrink-0" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
                    {cronometer.remaining}/{cronometer.limit} left
                  </span>
                )}
              </div>
              <p className="text-[9px] truncate" style={{ color: "var(--text-dim)" }}>{cronometer.detail}</p>
            </div>
            <button onClick={cronometer.sync} disabled={cronometer.syncing || !cronometer.canSync}
              title={cronometer.canSync ? "Sync now" : "Daily sync limit reached"}
              className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] transition-transform disabled:opacity-30"
              style={{ background: "rgba(0,229,160,0.1)", color: "var(--green)" }}>
              {cronometer.syncing ? "…" : "↻"}
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto relative z-10">
        <div key={dataVersion} className="max-w-6xl mx-auto px-8 py-8" style={{ minHeight: "100%" }}>
          {page === "overview" && <OverviewPage />}
          {page === "train" && <TrainPage />}
          {page === "progress" && <ProgressPage />}
          {page === "nutrition" && <NutritionPage />}
          {page === "coach" && <CoachPage />}
        </div>
      </main>
    </div>
  )
}
