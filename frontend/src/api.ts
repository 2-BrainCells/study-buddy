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

// Real learners are private: the server returns their token once and keeps only its hash,
// so this browser is the only place that can act as them. Demo learners have no token.
export type MyLearner = Learner & { token: string }
const MINE_KEY = "study-buddy.my-learners"

function readMine(): MyLearner[] {
  try {
    return JSON.parse(localStorage.getItem(MINE_KEY) ?? "[]")
  } catch {
    return []
  }
}
let mine = readMine()
export const myLearners = () => mine

function remember(l: MyLearner) {
  mine = [...mine.filter((m) => m.id !== l.id), l]
  try {
    localStorage.setItem(MINE_KEY, JSON.stringify(mine))
  } catch {
    // ponytail: storage blocked (private window): the learner lasts until this tab closes
  }
}

function auth(lid?: number): Record<string, string> {
  const token = mine.find((m) => m.id === lid)?.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function req<T>(path: string, init?: RequestInit, lid?: number): Promise<T> {
  const r = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...auth(lid) } })
  if (!r.ok) {
    const text = await r.text()
    let detail = text
    try {
      detail = JSON.parse(text).detail ?? text // FastAPI errors look like {"detail": "..."}
    } catch {
      // not JSON: show the raw text
    }
    throw new Error(`${detail} (${init?.method ?? "GET"} ${path}: ${r.status})`)
  }
  return r.json()
}
const post = <T,>(path: string, body: unknown, lid?: number) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) }, lid)

export const api = {
  learners: () => req<Learner[]>("/learners"),
  videos: () => req<Video[]>("/videos"),
  async createLearner(name: string, answers: Record<string, boolean>, invite: string) {
    const r = await post<{ learner_id: number; seeded_terms: number; token: string }>("/learners", { name, answers, invite })
    remember({ id: r.learner_id, name, questionnaire: answers, note_terms: 0, token: r.token })
    return r
  },
  async addNotes(id: number, text: string) {
    const r = await post<{ terms_added: number }>(`/learners/${id}/notes`, { text }, id)
    const me = mine.find((m) => m.id === id)
    if (me) remember({ ...me, note_terms: me.note_terms + r.terms_added })
    return r
  },
  plan: (lid: number, vid: number) => req<PlanItem[]>(`/learners/${lid}/videos/${vid}/plan`, undefined, lid),
  quiz: (vid: number) => req<Question[]>(`/videos/${vid}/quiz`),
  known: (lid: number, video_id: number, term_id: number, ts: number) =>
    post(`/learners/${lid}/known`, { video_id, term_id, ts }, lid),
  config: () => req<{ demo: boolean; invite: boolean }>("/config"),
  usage: () => req<Usage>("/usage"),
  dashboard: (vid: number) => req<Dashboard>(`/dashboard/videos/${vid}`),
  event: (e: { learner_id: number; video_id: number; type: EventType; term_id?: number; correct?: boolean; ts?: number }) =>
    post("/events", e, e.learner_id),
}
export const mediaUrl = (vid: number) => `/api/videos/${vid}/media`
export const captionsUrl = (vid: number) => `/api/videos/${vid}/captions.vtt`
