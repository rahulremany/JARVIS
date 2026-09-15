# Personal Health Coach App — Spec

## 1. Problem statement

Existing all-in-one apps (Vora, Bevel, MacroFactor Workouts) each break down on one of three requirements:

| Requirement | Vora | Bevel | MacroFactor |
|---|---|---|---|
| Deep nutrition/micronutrient tracking | Yes (broken onboarding) | Yes | Yes (best-in-class) |
| Native Garmin set/rep capture | Unknown/broken | No (Apple Watch only) | No (Health Connect only, no direct device link) |
| AI coaching layer | Yes (buggy) | Yes (subscription) | No |

None hit all three reliably for a **Garmin Venu X1** user. This spec defines a minimal personal app that does.

## 2. Goals

1. Log strength workouts (sets/reps/weight) with as little manual re-entry as possible, using the Garmin Training API.
2. Track nutrition (calories, macros, key micronutrients) with fast logging — specifically, photo-based meal analysis via Claude's vision capability.
3. Provide AI coaching (plan generation, daily/weekly feedback) using the Claude API, reasoning over logged workout and nutrition data.
4. Single source of truth (one database), so nutrition and training data can be queried together (e.g. "am I under-eating on lifting days").
5. Runs for one user (you) — not a multi-tenant SaaS. This drastically simplifies auth, billing, and scaling concerns.
6. **Full historical ingestion, not just going-forward logging.** On first connecting Garmin, backfill the complete available history — not just recovery/sleep/HRV, but all activity types Garmin exposes (strength sessions, cardio, steps, body composition if tracked, past workout plans). This gives the coaching layer long-term trend context (e.g. months of HRV baseline, historical training volume) rather than starting cold.

## 3. Non-goals

- Multi-user support, social features, leaderboards.
- Replacing Garmin's own recovery/sleep/HRV algorithms — pull that data in, don't recompute it.
- Building a mobile app store listing. A private web app (PWA) installed to your phone's home screen is sufficient and far less overhead than native iOS/Android development.

## 4. Architecture overview

**Data flow, four components:**

1. **Garmin Connect** (watch + API) ↔ **Sync Service** (scheduled job) — pulls recovery/sleep/HRV data, and (long-term) pushes/pulls structured workouts.
2. **PWA frontend** (meal photo capture + workout logging) → **App Backend** (API + business logic) — handles all user input.
3. Both the Sync Service and the App Backend read/write to a single **Core Database** (Postgres or SQLite) — the shared source of truth for workouts, nutrition logs, recovery data, and coach notes.
4. **Coaching Service** (prompt building, structured output) ↔ **Claude API** (vision + text, structured JSON) — reads from the Core Database, calls Claude, writes recommendations back to the Core Database.

In short: Garmin and the user both feed the same database through two separate paths (sync job vs. app backend), and the coaching service is a third component that only reads from that database and calls out to Claude — it doesn't talk to Garmin or the frontend directly.

## 5. Core components

### 5.1 Garmin integration
- Register for the **Garmin Connect Developer Program** (Training API + Health API).
  - Training API: push structured workouts (exercises/sets/reps/target weight) to the watch calendar.
  - Health API: pull back sleep, HRV, recovery, stress, steps, activity summaries.
  - **Known limitation:** Garmin's Training API does not reliably return completed strength-session set/rep detail after the fact. Two ways to work around this:
    1. Use a Garmin Connect IQ companion watch app (custom-built) that logs sets/reps directly and pushes them via a Connect IQ Communications API to your backend, bypassing the Training API gap entirely. This is the "real" fix but requires learning Garmin's Connect IQ SDK (Monkey C language).
    2. Fallback: log sets/reps manually in the app UI during/after the workout (mirrors what Bevel/MacroFactor users already do on Garmin). Ship this first; build the Connect IQ app as a v2 stretch goal.
- Pull `.fit` file activity summaries (duration, calories, heart rate) automatically — this part works today via the standard Health API and needs no workaround.
- **Historical backfill (one-time, on first connect):** Garmin's Health API supports paginated historical pulls, not just going-forward sync. On initial connection, run a backfill job that fetches the complete available history for every data type the API exposes for this account — sleep, HRV, resting HR, stress, steps, body composition (if logged), and past activity summaries (cardio and any previously-recorded strength sessions). Rate-limit this job (Garmin's API has request caps) and run it as a background task, not inline with onboarding — expect it to take from minutes to hours depending on how many years of data exist on the account. Store it in the same `garmin_recovery` / `workouts` tables as ongoing sync, just tagged with an earlier date range. This backfill is what gives the coaching layer real trend context (e.g. "your HRV baseline over the past year" or "your squat volume this training block vs. six months ago") instead of only ever seeing the last two weeks.

### 5.2 Nutrition logging
- Primary method: **photo-based logging via Claude's vision capability** — snap a meal prep photo, Claude estimates macros directly (see Section 9.1). No separate food database required for this path.
- Fallback methods: barcode scan against USDA FoodData Central / Open Food Facts (free, open datasets), or manual entry, for cases where a photo isn't practical (e.g. a packaged product with a label).
- Store daily targets (calories/macros/micronutrients) computed once, adjustable manually — don't over-engineer an adaptive algorithm for a v1.

### 5.3 AI coaching layer
- Not a chatbot bolted on — a service that:
  1. Builds a structured prompt from your recent logs (last 7–14 days of training + nutrition + Garmin recovery data).
  2. Calls the Claude API, asking for **structured JSON output** (e.g. `{ recommendation, reasoning, flags }`) rather than free text, so the UI can render it predictably.
  3. Runs on a schedule (e.g. daily) or on-demand when you open the app.
- See Section 9 for concrete request patterns (meal-photo analysis vs. lifting-data analysis).

### 5.4 Data model (minimal)
- `workouts(id, date, source[manual|garmin], exercise, sets JSON[reps, weight, rpe])`
- `nutrition_logs(id, datetime, food_name, calories, protein, carbs, fat, micronutrients JSON, source[photo|barcode|manual])`
- `daily_targets(date, calories, protein, carbs, fat)`
- `garmin_recovery(date, hrv, sleep_score, stress_score, resting_hr)`
- `coach_notes(date, recommendation, reasoning, flags JSON)`

### 5.5 Frontend
- A PWA (installable web app) is the pragmatic choice for a solo project — one codebase, works on your phone's home screen, no App Store review process, no native build pipeline.
- Framework: React + a lightweight backend (FastAPI/Node) is a reasonable default; swap for whatever you're already comfortable with.

## 6. Build phases

**Phase 1 (MVP, ~2–3 weekends):**
- Manual workout logging (sets/reps/weight) + meal-photo logging via Claude vision.
- Garmin Health API pull for recovery/sleep (read-only, no push).
- Single dashboard showing both side by side.

**Phase 2:**
- Claude coaching layer (daily/weekly summary + recommendation, per Section 9).
- Barcode/manual fallback for nutrition logging where photos aren't practical.

**Phase 3 (stretch):**
- Custom Garmin Connect IQ watch app for native on-wrist set/rep logging, closing the gap that no consumer app currently solves for Garmin users.

## 7. Hardware & environment context

**Environment:** MacBook Pro, Apple M5 (base, not Pro/Max), 16GB unified memory, 1TB SSD (storage is not a constraint — memory, and the fact that dev tools for a separate project ("JARVIS") will run concurrently, are the real constraints). Coaching calls are infrequent (not a constantly-running process), and a planned eventual merge or handoff into JARVIS is expected.

**Decision: use the Claude API for the coaching layer, not a self-hosted model.**

Reasoning:
- Coaching calls are low-frequency (roughly daily), so token cost for structured JSON summaries is trivial — a few cents a month at most, not worth optimizing away.
- A 16GB base-M5 machine has no memory to spare once JARVIS's own dev environment (IDE, language servers, build tools) is running; a self-hosted model competes directly for that headroom even when quantized small.
- Output quality on nuanced judgment calls (e.g. "should this week be a deload") is meaningfully better from Claude than a small local model, and vision quality for meal-photo macro estimation is significantly better.
- No local footprint, no model management/updates, no quantization tradeoffs to babysit.

**If self-hosting is ever wanted anyway** (offline use, cost at higher volume, or preference): Qwen3 8B q4_K_M (~4.5–5GB resident) is the fallback pick for text-only reasoning, with Qwen3 4B (~2.5GB) as a lighter option. Note a local model would lose the vision-based meal-photo path Section 9.1 relies on unless paired with a separate vision model — this is a meaningful capability drop, not just a cost/quality tradeoff.

**Design for the eventual merge — decouple now, don't rewrite later:**
- The coaching layer is a standalone service with a narrow JSON-in/JSON-out API, not logic embedded inside the fitness app's backend.
- It calls the Claude API directly (`api.anthropic.com`). This same pattern is exactly what JARVIS will likely use, so the two projects can share one integration point.
- Keep the workouts/nutrition/recovery database as its own component with a simple query interface, independent of both the fitness app UI and the coaching service. This lets it become shared long-term memory either app can read from.
- Result: merging into JARVIS later becomes either (a) JARVIS calls the existing coaching API as one more tool, or (b) JARVIS's own Claude calls take over the coaching service's role directly, with the database persisting as shared state either way.

## 8. Claude coaching integration — implementation patterns

Two distinct jobs, two distinct input shapes. Don't force both through the same call.

### 8.1 Meal analysis (vision input)
Send the meal photo directly to Claude — no food database needed for this path, Claude estimates macros from the image itself.

```javascript
const response = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "claude-sonnet-5",
    max_tokens: 1000,
    system: `You are a nutrition coach analyzing a meal photo. Estimate
      calories, protein, carbs, and fat. Be direct about uncertainty —
      if portion size is ambiguous, say so and give a range rather than
      a false-precision single number. Respond ONLY with JSON:
      { "calories": [min, max], "protein_g": [min, max], "carbs_g": [min, max],
        "fat_g": [min, max], "confidence": "low|medium|high", "notes": "..." }`,
    messages: [{
      role: "user",
      content: [
        { type: "image", source: { type: "base64", media_type: "image/jpeg", data: photoBase64 } },
        { type: "text", text: "Estimate the macros for this meal." }
      ]
    }]
  })
});
```

### 8.2 Lifting analysis (structured data input)
Send logged sets/reps/weight as JSON, not photos. Precision matters more than convenience here.

```javascript
const workoutHistory = {
  last_14_days: [ /* pulled from your workouts table */ ],
  recovery: [ /* pulled from Garmin health API: HRV, sleep, resting HR */ ],
  nutrition_summary: [ /* daily calorie/protein totals from meal logs */ ]
};

const response = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "claude-sonnet-5",
    max_tokens: 1500,
    system: `You are a strength coach reviewing training and recovery data.
      Look for: stalled lifts, volume trending down without a deload reason,
      protein intake too low to support the training load, recovery scores
      that suggest overreaching. Be specific and cite the actual numbers you're
      reacting to. Respond ONLY with JSON:
      { "flags": [{"issue": "...", "evidence": "...", "severity": "low|medium|high"}],
        "recommendation": "...", "reasoning": "..." }`,
    messages: [{
      role: "user",
      content: `Here is my last 14 days of data:\n${JSON.stringify(workoutHistory)}`
    }]
  })
});
```

### 8.3 Design notes
- Both calls return structured JSON so the app UI can render flags/recommendations predictably rather than parsing free text.
- Keep these as two separate API calls with separate system prompts, not one combined "do everything" prompt — each does a distinct kind of reasoning (visual estimation vs. numeric trend analysis) and stays more accurate when scoped narrowly.
- A third optional call — a daily/weekly summary — can take the *output* of both of the above (not raw data) and produce a single combined coaching note. This keeps token usage low since it's reasoning over two small JSON summaries, not the full raw history.
- `claude-sonnet-5` is a reasonable default for both call types; drop to a smaller/cheaper model later if cost ever becomes worth optimizing (unlikely at personal-use volume).