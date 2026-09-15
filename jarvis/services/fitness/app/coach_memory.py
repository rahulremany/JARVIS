"""Plain-text long-term memory for the coach.

One file, `coach_memory.txt`, readable and editable by hand. Two sections:

  MEMORY — durable facts the coach chose to keep (goals, injuries, equipment,
           schedule, preferences). Written only when Claude calls `remember`.
  RECENT — a rolling transcript of the last few exchanges, so a new session
           picks up mid-conversation instead of cold.

Deliberately NOT a log of everything. Workouts, sets, macros and recovery
already live in the database and are injected into the prompt from there —
duplicating them here would burn context to say the same thing twice. This
file is for what only ever gets said out loud: "my left shoulder clicks on
overhead press", "I train at a commercial gym", "I'm cutting until October".

Size is bounded by trimming oldest-first, so it can't grow without limit or
quietly inflate every prompt.
"""
import os
import re
from datetime import datetime

MEMORY_PATH = os.environ.get(
    "COACH_MEMORY_PATH", os.path.join(os.path.dirname(__file__), "..", "coach_memory.txt")
)

# Characters, not tokens — roughly 4:1, so these caps are ~2k and ~3k tokens.
MEMORY_CAP = 8000
RECENT_CAP = 12000
TURN_CAP = 400  # per logged message, so one rambling turn can't eat the file

PLACEHOLDER = "(nothing yet)"
HEADER = "# Volt coach memory — plain text, safe to edit by hand.\n"
MEMORY_MARK = "## MEMORY (durable facts)"
RECENT_MARK = "## RECENT (rolling transcript)"


def _read_raw() -> str:
    try:
        with open(MEMORY_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _split(raw: str) -> tuple[list[str], list[str]]:
    """Returns (memory_lines, recent_lines). Tolerates a hand-edited or absent
    file rather than throwing — this is a text file a human may have touched."""
    memory: list[str] = []
    recent: list[str] = []
    bucket = None
    for line in raw.splitlines():
        if line.startswith(MEMORY_MARK):
            bucket = memory
            continue
        if line.startswith(RECENT_MARK):
            bucket = recent
            continue
        if line.startswith("#") or not line.strip():
            continue
        if line.strip() == PLACEHOLDER:  # written when a section is empty
            continue
        if bucket is not None:
            bucket.append(line.rstrip())
    return memory, recent


def _trim(lines: list[str], cap: int) -> list[str]:
    """Drops oldest lines until the section fits. Newest wins — an old chat
    turn is the most expendable thing in the file."""
    while lines and sum(len(l) + 1 for l in lines) > cap:
        lines.pop(0)
    return lines


def _write(memory: list[str], recent: list[str]) -> None:
    body = (
        f"{HEADER}\n{MEMORY_MARK}\n"
        + ("\n".join(_trim(memory, MEMORY_CAP)) or PLACEHOLDER)
        + f"\n\n{RECENT_MARK}\n"
        + ("\n".join(_trim(recent, RECENT_CAP)) or PLACEHOLDER)
        + "\n"
    )
    os.makedirs(os.path.dirname(os.path.abspath(MEMORY_PATH)), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        f.write(body)


def _clean(text: str) -> str:
    """Collapses a message to one line so the file stays greppable."""
    flat = re.sub(r"\s+", " ", (text or "").strip())
    return flat[:TURN_CAP] + ("…" if len(flat) > TURN_CAP else "")


def list_facts() -> list[dict]:
    """The durable section as structured rows, for the UI and for `forget`."""
    memory, _ = _split(_read_raw())
    rows = []
    for i, line in enumerate(memory):
        m = re.match(r"\[(\d{4}-\d{2}-\d{2})\]\s*(.*)", line)
        rows.append({"index": i, "date": m.group(1) if m else "", "text": m.group(2) if m else line})
    return rows


def forget(match: str) -> str:
    """Drops facts containing `match`. This is how a fact gets corrected: the
    coach forgets the stale one and remembers the new one, so contradictions
    don't accumulate ('shoulder hurts' sitting next to 'shoulder is fine')."""
    memory, recent = _split(_read_raw())
    needle = match.lower().strip()
    if not needle:
        return "nothing to forget"

    keep = [l for l in memory if needle not in l.lower()]
    dropped = len(memory) - len(keep)
    if dropped:
        _write(keep, recent)
    return f"forgot {dropped} fact(s)" if dropped else "no matching fact found"


def delete_fact(index: int) -> bool:
    memory, recent = _split(_read_raw())
    if not (0 <= index < len(memory)):
        return False
    memory.pop(index)
    _write(memory, recent)
    return True


def remember(fact: str) -> str:
    """Adds a durable fact. Ignores a near-duplicate of something already known
    so repeated mentions don't stack up."""
    memory, recent = _split(_read_raw())
    fact = _clean(fact)
    if not fact:
        return "empty fact ignored"

    key = re.sub(r"[^a-z0-9 ]", "", fact.lower())
    for existing in memory:
        if key and key in re.sub(r"[^a-z0-9 ]", "", existing.lower()):
            return "already remembered"

    memory.append(f"[{datetime.now():%Y-%m-%d}] {fact}")
    _write(memory, recent)

    # Durable facts are the one thing we must not lose to a blind trim, so
    # merge them down before the cap starts evicting the oldest.
    if sum(len(l) + 1 for l in memory) > MEMORY_CAP * 0.8:
        compact()
    return "remembered"


COMPACT_PROMPT = """You are compacting a strength coach's long-term memory about \
one athlete. Merge related lines, drop anything superseded by a newer line \
(an old injury that later resolved, a goal that was replaced), and cut \
anything that is a passing detail rather than a durable fact.

Keep every fact that still matters: injuries and movement restrictions, goals \
and their timelines, equipment and gym access, schedule constraints, dietary \
restrictions, and coaching approaches that were explicitly said to work or not \
work. Preserve the [YYYY-MM-DD] date prefix of the most recent line each merged \
fact came from.

Return ONLY the compacted lines, one fact per line, no commentary, no bullets."""


def compact() -> str:
    """Rewrites the durable section into fewer, denser lines using Claude.
    Falls back to leaving memory untouched if the call fails — a failed
    compaction must never destroy the file."""
    memory, recent = _split(_read_raw())
    if not memory:
        return "nothing to compact"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "no ANTHROPIC_API_KEY — skipped compaction"

    try:
        import anthropic

        response = anthropic.Anthropic(api_key=api_key).messages.create(
            model="claude-sonnet-5",
            max_tokens=2000,
            system=COMPACT_PROMPT,
            messages=[{"role": "user", "content": "\n".join(memory)}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        compacted = [l.strip() for l in text.splitlines() if l.strip()]
    except Exception as e:
        return f"compaction failed, memory left as-is: {e}"

    if not compacted:
        return "compaction returned nothing, memory left as-is"

    _write(compacted, recent)
    return f"compacted {len(memory)} facts into {len(compacted)}"


def log_exchange(user_text: str, assistant_text: str) -> None:
    """Appends one round-trip to the rolling transcript."""
    memory, recent = _split(_read_raw())
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    if user_text:
        recent.append(f"[{stamp}] me: {_clean(user_text)}")
    if assistant_text:
        recent.append(f"[{stamp}] coach: {_clean(assistant_text)}")
    _write(memory, recent)


def as_prompt_context() -> str:
    memory, recent = _split(_read_raw())
    if not memory and not recent:
        return ""
    return (
        "What you remember about this user from previous sessions "
        "(the workout data below is the authoritative record; this is "
        "context that only came up in conversation):\n\n"
        f"{MEMORY_MARK}\n" + ("\n".join(memory) or PLACEHOLDER) + "\n\n"
        f"{RECENT_MARK}\n" + ("\n".join(recent[-40:]) or PLACEHOLDER)
    )
