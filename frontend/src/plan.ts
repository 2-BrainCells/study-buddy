import type { PlanItem, Question } from "@/api"

export const MAX_PAUSES = 5 // ponytail: fixed cap per video; scale with duration for full 76-min lectures

export type Stop = { ts: number; items: PlanItem[] }

/** This learner's new terms grouped by pause point; the first `cap` stops pause, the rest wait for the end. */
export function buildStops(plan: PlanItem[], cap = MAX_PAUSES): { stops: Stop[]; queued: PlanItem[] } {
  const byTs = new Map<number, PlanItem[]>()
  for (const p of plan) if (p.status === "new") byTs.set(p.pause_ts, [...(byTs.get(p.pause_ts) ?? []), p])
  const all = [...byTs].sort((a, b) => a[0] - b[0]).map(([ts, items]) => ({ ts, items }))
  return { stops: all.slice(0, cap), queued: all.slice(cap).flatMap((s) => s.items) }
}

/**
 * The stop that playback passed between two checks, if any. Rewinds never fire a stop; the Player resets
 * `prev` on seeks, so any forward gap here is real playback, however long (hidden windows check rarely).
 */
export function crossed(stops: Stop[], fired: Set<number>, prev: number, now: number): Stop | undefined {
  if (now < prev) return undefined
  return stops.find((s) => !fired.has(s.ts) && prev < s.ts && s.ts <= now)
}

/** n questions, one per term: this learner's new terms first (in video order), then the rest. */
export function pickQuiz(questions: Question[], plan: PlanItem[], n = 5): Question[] {
  const first = new Map<number, Question>()
  for (const q of questions) if (!first.has(q.term_id)) first.set(q.term_id, q)
  const order = [...plan].sort(
    (a, b) => Number(b.status === "new") - Number(a.status === "new") || a.pause_ts - b.pause_ts,
  )
  return order.flatMap((p) => first.get(p.term_id) ?? []).slice(0, n)
}
