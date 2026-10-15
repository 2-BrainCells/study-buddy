export type PlanItem = {
  term_id: number
  term: string
  pause_ts: number
  explanation: string
  status: "known" | "new"
  reason: string
  nearest: string | null
  sim: number | null
}
export type Question = { id: number; term_id: number; question: string; options: string[]; answer: number }
export type Video = { id: number; title: string; source: string; licence: string; duration_s: number }
export type Learner = { id: number; name: string; questionnaire: Record<string, boolean>; note_terms: number }
type EventType = "pause" | "glance" | "quiz_answer"

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
  event: (e: { learner_id: number; video_id: number; type: EventType; term_id?: number; correct?: boolean; ts?: number }) =>
    post("/events", e),
}
export const mediaUrl = (vid: number) => `/api/videos/${vid}/media`
export const captionsUrl = (vid: number) => `/api/videos/${vid}/captions.vtt`
