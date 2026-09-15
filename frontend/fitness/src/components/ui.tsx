import type { ReactNode } from "react"

export function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`text-[10px] uppercase tracking-[0.14em] font-500 ${className}`}
      style={{ color: "var(--text-muted)" }}>
      {children}
    </p>
  )
}

export function SourceBadge({ source }: { source: "garmin" | "claude" }) {
  const cfg = {
    garmin: { bg: "rgba(77,158,255,0.1)", color: "var(--blue)", border: "rgba(77,158,255,0.2)", label: "Garmin" },
    claude: { bg: "rgba(124,95,255,0.12)", color: "var(--purple)", border: "rgba(124,95,255,0.25)", label: "Claude AI" },
  }[source]
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-wider"
      style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}>
      <span className="pulse" style={{ width: 4, height: 4, borderRadius: "50%", background: cfg.color, display: "inline-block" }} />
      {cfg.label}
    </span>
  )
}

export function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass px-3 py-2" style={{ borderRadius: 10, border: "1px solid var(--border-bright)" }}>
      <p className="text-[10px] mb-1" style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} className="text-xs font-600" style={{ color: p.color, fontFamily: "var(--font-mono)" }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

export function RecoveryRing({ score, size = 140 }: { score: number; size?: number }) {
  const stroke = 9, r = (size - stroke) / 2
  const circ = 2 * Math.PI * r, dash = (score / 100) * circ
  const color = score >= 67 ? "var(--green)" : score >= 34 ? "var(--orange)" : "var(--red)"
  const glow = score >= 67 ? "rgba(0,229,160,0.35)" : score >= 34 ? "rgba(255,140,66,0.35)" : "rgba(255,77,94,0.35)"
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      {/* A radial gradient fades to transparent on its own — no separate blur
          filter needed, which avoids a compositing artifact where a blurred
          layer nested inside this card's backdrop-filter renders a faint
          square edge in Chromium/WebKit. */}
      <div className="absolute inset-0" style={{ background: `radial-gradient(circle, ${glow}, transparent 70%)` }} />
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)", position: "relative", zIndex: 1 }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono font-700" style={{ fontSize: "1.9rem", color, lineHeight: 1, fontFamily: "var(--font-mono)", filter: `drop-shadow(0 0 10px ${color})` }}>
          {score}
        </span>
        <span className="text-[9px] uppercase tracking-widest mt-1" style={{ color: "var(--text-muted)" }}>Recovery</span>
      </div>
    </div>
  )
}

export function StatCard({ label, value, unit, sub, color = "var(--text)" }: {
  label: string; value: string | number; unit?: string; sub?: string; color?: string
}) {
  return (
    <div className="glass p-4">
      <Label>{label}</Label>
      <p className="font-mono font-700 mt-2" style={{ fontSize: "2rem", lineHeight: 1, color, fontFamily: "var(--font-mono)" }}>
        {value}{unit && <span className="text-sm opacity-50 ml-1">{unit}</span>}
      </p>
      {sub && <p className="text-[11px] mt-1.5" style={{ color: "var(--text-muted)" }}>{sub}</p>}
    </div>
  )
}

export function PageHeader({ eyebrow, title, accent, children }: {
  eyebrow: string; title: string; accent?: string; children?: ReactNode
}) {
  return (
    <div className="flex items-end justify-between">
      <div>
        <p className="text-[11px] uppercase tracking-[0.15em]" style={{ color: "var(--text-muted)" }}>{eyebrow}</p>
        <h1 className="font-800 mt-1 leading-none" style={{ fontFamily: "var(--font-display)", fontSize: "2.2rem" }}>
          <span className="grad-text">{title}</span>
          {accent && <span className="grad-red">{accent}</span>}
        </h1>
      </div>
      {children && <div className="flex items-center gap-3">{children}</div>}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="glass p-8 text-center">
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>{children}</p>
    </div>
  )
}

export function Spinner({ size = 16, color = "var(--purple)" }: { size?: number; color?: string }) {
  return (
    <div className="rounded-full border-2 border-t-transparent shrink-0"
      style={{
        width: size, height: size,
        borderColor: color, borderTopColor: "transparent",
        animation: "spin 0.9s linear infinite",
      }} />
  )
}
