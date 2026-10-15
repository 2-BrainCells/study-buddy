import { expect, it } from "vitest"
import type { PlanItem, Question } from "@/api"
import { buildStops, crossed, pickQuiz } from "@/plan"

const item = (term_id: number, pause_ts: number, status: "new" | "known" = "new"): PlanItem => ({
  term_id, term: `t${term_id}`, pause_ts, explanation: "", status, reason: "", nearest: null, sim: null,
})
const q = (id: number, term_id: number): Question => ({ id, term_id, question: "", options: [], answer: 0 })

it("groups terms that share a pause and skips known ones", () => {
  const { stops } = buildStops([item(1, 78), item(2, 78), item(3, 90, "known")])
  expect(stops).toEqual([{ ts: 78, items: [item(1, 78), item(2, 78)] }])
})

it("queues stops past the cap for the end", () => {
  const { stops, queued } = buildStops([item(1, 10), item(2, 20), item(3, 30)], 2)
  expect(stops.map((s) => s.ts)).toEqual([10, 20])
  expect(queued.map((p) => p.term_id)).toEqual([3])
})

it("fires once during playback, never on a rewind", () => {
  const stops = [{ ts: 10, items: [item(1, 10)] }]
  expect(crossed(stops, new Set(), 9.99, 10.01)).toBe(stops[0])
  expect(crossed(stops, new Set([10]), 9.99, 10.01)).toBeUndefined()
  expect(crossed(stops, new Set(), 10.5, 9.5)).toBeUndefined()
})

it("still fires when a hidden window checks the clock rarely", () => {
  const stops = [{ ts: 10, items: [item(1, 10)] }]
  expect(crossed(stops, new Set(), 8.2, 11.9)).toBe(stops[0])
})

it("quiz asks about new terms first, one question per term", () => {
  const plan = [item(1, 10, "known"), item(2, 20), item(3, 30)]
  const picked = pickQuiz([q(1, 1), q(2, 1), q(3, 2), q(4, 3)], plan, 2)
  expect(picked.map((x) => x.id)).toEqual([3, 4])
})
