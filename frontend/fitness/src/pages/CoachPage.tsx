import { useEffect, useRef, useState } from "react"
import { Label, SourceBadge, PageHeader, Spinner } from "../components/ui"
import { MarkdownMessage } from "../components/MarkdownMessage"
import { sendCoachChat, getCoachMemory, deleteCoachMemory } from "../lib/api"
import type { ChatMessage, MemoryFact } from "../lib/api"

const STARTER_PROMPTS = [
  "How should I approach my next session?",
  "Am I progressing on bench?",
  "Is it time for a deload?",
  "Log 6oz chicken and a cup of rice",
]

export function CoachPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const [memory, setMemory] = useState<MemoryFact[]>([])
  const [showMemory, setShowMemory] = useState(false)

  // Refreshed after each reply — the coach may have remembered something new
  // during that turn, and memory you can't see is memory you can't correct.
  const loadMemory = () =>
    getCoachMemory()
      .then(f => setMemory(f.filter(x => x.text && x.text !== "(nothing yet)")))
      .catch(console.error)

  useEffect(() => { loadMemory() }, [])

  useEffect(() => {
    if (messages.length === 0) return
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages, sending])

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    const next: ChatMessage[] = [...messages, { role: "user", content: trimmed }]
    setMessages(next)
    setInput("")
    setSending(true)
    setError(null)
    try {
      const { reply } = await sendCoachChat(next)
      setMessages([...next, { role: "assistant", content: reply }])
      loadMemory()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reach the coach")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col gap-6" style={{ height: "100%" }}>
      <PageHeader eyebrow="Ask Anything" title="Coach">
        <button onClick={() => setShowMemory(s => !s)}
          className="px-3 py-1.5 rounded-lg text-[11px] font-500"
          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
          Memory · {memory.length}
        </button>
        <SourceBadge source="claude" />
      </PageHeader>

      {showMemory && (
        <div className="glass px-6 py-5">
          <Label>What the coach remembers about you between sessions</Label>
          {memory.length === 0 ? (
            <p className="text-sm mt-3" style={{ color: "var(--text-muted)" }}>
              Nothing yet — mention an injury, a goal, your schedule or equipment and it'll be kept.
            </p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {memory.map(f => (
                <li key={f.index} className="flex items-start gap-3 text-sm">
                  <span className="font-mono text-[10px] shrink-0 mt-1" style={{ color: "var(--text-dim)" }}>{f.date}</span>
                  <span className="flex-1" style={{ color: "var(--text-muted)" }}>{f.text}</span>
                  <button onClick={() => deleteCoachMemory(f.index).then(loadMemory)}
                    title="Forget this" className="shrink-0 text-xs px-2" style={{ color: "var(--text-dim)" }}>×</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="glass flex flex-col flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4" style={{ minHeight: 0 }}>
          {messages.length === 0 && (
            <div className="flex flex-col gap-3 m-auto w-full" style={{ maxWidth: 560 }}>
              <Label>The coach can read your logged sessions and recovery — and log meals or edit workouts for you.</Label>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {STARTER_PROMPTS.map(p => (
                  <button key={p} onClick={() => send(p)}
                    className="text-left px-4 py-3 text-sm rounded-xl transition-all"
                    style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className="flex" style={{ justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              <div className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
                style={{
                  maxWidth: "76%",
                  ...(m.role === "user"
                    ? { background: "linear-gradient(135deg, #ff4d5e, #ff8c42)", color: "#fff" }
                    : { background: "rgba(124,95,255,0.07)", border: "1px solid rgba(124,95,255,0.18)", color: "var(--text)" }),
                }}>
                {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : m.content}
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex justify-start">
              <div className="px-4 py-3 rounded-2xl text-sm flex items-center gap-2"
                style={{ background: "rgba(124,95,255,0.07)", border: "1px solid rgba(124,95,255,0.18)", color: "var(--text-muted)" }}>
                <Spinner size={12} />
                thinking…
              </div>
            </div>
          )}

          {error && <p className="text-xs" style={{ color: "var(--red)" }}>{error}</p>}

          <div ref={bottomRef} />
        </div>

        <div className="px-6 py-4 border-t shrink-0" style={{ borderColor: "var(--border)" }}>
          <div className="flex gap-3">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && send(input)}
              placeholder="Ask your coach anything…"
              className="flex-1 text-sm outline-none px-4 py-3 rounded-xl"
              style={{ background: "rgba(255,255,255,0.04)", border: "1px solid var(--border)", color: "var(--text)" }} />
            <button onClick={() => send(input)} disabled={sending || !input.trim()}
              className="px-6 rounded-xl font-700 text-sm transition-all"
              style={{
                background: "linear-gradient(135deg, #7c5fff, #c084fc)",
                color: "#fff", fontFamily: "var(--font-display)",
                opacity: sending || !input.trim() ? 0.45 : 1,
              }}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
