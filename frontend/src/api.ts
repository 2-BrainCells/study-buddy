export type PlanItem = {
  term_id: number
  term: string
  pause_ts: number
  explanation: string
  status: "known" | "new"
  reason: string
  nearest: string | null
  sim: number | null
  mentions: number // how often the transcript says the term; ranks which stops pause
}
export type Question = { id: number; term_id: number; question: string; options: string[]; answer: number }
export type Video = { id: number; title: string; source: string; licence: string; duration_s: number }
export type Learner = { id: number; name: string; questionnaire: Record<string, boolean>; note_terms: number }
type EventType = "pause" | "glance" | "quiz_answer"

export type StageUsage = {
  stage: string; model: string; requests: number; input_tokens: number; output_tokens: number
  retries_429: number; avg_latency_ms: number; max_latency_ms: number; cost_usd: number | null
}
type TfTotals = { requests: number; errors: number; total_tokens: number; cached_tokens: number; cost: number }
export type Quota =
  | { available: false; reason: string }
  | { available: true; daily_limit_usd: number | null; daily_used_usd: number | null; daily_remaining_usd: number | null
      reset_at: string | null; rpm_limit: number | null; today: TfTotals; last_24_hours: TfTotals }
export type Usage = {
  stages: StageUsage[]
  totals: { requests: number; input_tokens: number; output_tokens: number; retries_429: number; cost_usd: number }
  lecture: { title: string; duration_s: number; tokens: number; cost_usd: number; tokens_per_hour: number | null
             cost_per_hour_usd: number | null } | null
  learners: { learner_id: number; name: string; requests: number; tokens: number; cost_usd: number }[]
  quota: Quota
}
export type DashTerm = {
  term_id: number; term: string; pause_ts: number; new_for: number; paused: number; marked_known: number
  answered: number; wrong: number; score: number
}
export type Dashboard = {
  learners: number; sessions: number; pauses: number; quiz_answered: number; quiz_correct: number; terms: DashTerm[]
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...init })
  if (!r.ok) throw new Error(`${init?.method ?? "GET"} ${path}: ${r.status} ${await r.text()}`)
  return r.json()
}
const post = <T,>(path: string, body: unknown) => req<T>(path, { method: "POST", body: JSON.stringify(body) })

export const api = {
  learners: () => req<Learner[]>("/learners"),
  videos: () => req<Video[]>("/videos"),
  createLearner: (name: string, answers: Record<string, boolean>) =>
    post<{ learner_id: number; seeded_terms: number }>("/learners", { name, answers }),
  addNotes: (id: number, text: string) => post<{ terms_added: number }>(`/learners/${id}/notes`, { text }),
  plan: (lid: number, vid: number) => req<PlanItem[]>(`/learners/${lid}/videos/${vid}/plan`),
  quiz: (vid: number) => req<Question[]>(`/videos/${vid}/quiz`),
  known: (lid: number, video_id: number, term_id: number, ts: number) =>
    post(`/learners/${lid}/known`, { video_id, term_id, ts }),
  usage: () => req<Usage>("/usage"),
  dashboard: (vid: number) => req<Dashboard>(`/dashboard/videos/${vid}`),
  event: (e: { learner_id: number; video_id: number; type: EventType; term_id?: number; correct?: boolean; ts?: number }) =>
    post("/events", e),
}
export const mediaUrl = (vid: number) => `/api/videos/${vid}/media`
export const captionsUrl = (vid: number) => `/api/videos/${vid}/captions.vtt`
