import type { PlanItem, Question } from "@/api"

export const MAX_PAUSES = 5 // ponytail: fixed cap per video; scale with duration for full 76-min lectures

export type Stop = { ts: number; items: PlanItem[] }

/**
 * This learner's new terms grouped by pause point. The `cap` stops whose terms the lecture mentions most
 * pause (ties go to the earlier stop); the rest wait for the end. Both lists are in video order.
 */
export function buildStops(plan: PlanItem[], cap = MAX_PAUSES): { stops: Stop[]; queued: PlanItem[] } {
  const byTs = new Map<number, PlanItem[]>()
  for (const p of plan) if (p.status === "new") byTs.set(p.pause_ts, [...(byTs.get(p.pause_ts) ?? []), p])
  const all = [...byTs].sort((a, b) => a[0] - b[0]).map(([ts, items]) => ({ ts, items }))
  const weight = (s: Stop) => Math.max(...s.items.map((i) => i.mentions))
  const chosen = new Set([...all].sort((a, b) => weight(b) - weight(a) || a.ts - b.ts).slice(0, cap))
  return { stops: all.filter((s) => chosen.has(s)), queued: all.filter((s) => !chosen.has(s)).flatMap((s) => s.items) }
}

/**
 * The stop that playback passed between two checks, if any. Rewinds never fire a stop; the Player resets
 * `prev` on seeks, so any forward gap here is real playback, however long (hidden windows check rarely).
 */
export function crossed(stops: Stop[], fired: Set<number>, prev: number, now: number): Stop | undefined {
  if (now < prev) return undefined
  return stops.find((s) => !fired.has(s.ts) && prev < s.ts && s.ts <= now)
}

/** "m:ss" for a time in seconds. */
export const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`

/** Learner-facing text for a plan reason: why a term pauses, or why it was skipped. */
export function reasonText(reason: string): string {
  if (reason.startsWith("notes: ")) return `In your notes: “${reason.slice(7)}”`
  const text: Record<string, string> = {
    "not in notes": "Not covered in your notes",
    "not checked against notes": "No notes cover it yet",
    "in your notes": "In your notes",
    "from your questionnaire": "From your questionnaire",
    "you marked it known": "You marked it known",
  }
  return text[reason] ?? reason // ponytail: unknown reasons shown as-is, so a new backend reason is visible
}

export const TOPICS: Record<string, string> = {
  calculus: "calculus",
  linear_algebra: "linear algebra",
  probability: "probability",
  ml_basics: "ML basics",
  python: "Python",
}

/** "calculus, Python" from questionnaire answers, in questionnaire order. */
export const comfortableWith = (answers: Record<string, boolean>) =>
  Object.keys(TOPICS).filter((k) => answers[k]).map((k) => TOPICS[k]).join(", ")

export const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()

/** n questions, one per term: this learner's new terms first (in video order), then the rest. */
export function pickQuiz(questions: Question[], plan: PlanItem[], n = 5): Question[] {
  const first = new Map<number, Question>()
  for (const q of questions) if (!first.has(q.term_id)) first.set(q.term_id, q)
  const order = [...plan].sort(
    (a, b) => Number(b.status === "new") - Number(a.status === "new") || a.pause_ts - b.pause_ts,
  )
  return order.flatMap((p) => first.get(p.term_id) ?? []).slice(0, n)
}
