import { afterEach, expect, it, vi } from "vitest"
import { api, myLearners } from "@/api"

// No browser here: localStorage is missing, so api.ts keeps learners in memory (its private-window fallback).
function stubFetch(body: unknown, status = 200) {
  const fetch = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal("fetch", fetch)
  return fetch
}
afterEach(() => vi.unstubAllGlobals())

it("remembers a new learner's token and sends it only for that learner", async () => {
  stubFetch({ learner_id: 7, seeded_terms: 0, token: "secret-7" })
  await api.createLearner("Priya", {}, "letmein")
  expect(myLearners().map((l) => l.id)).toContain(7)

  const fetch = stubFetch([])
  await api.plan(7, 1)
  await api.plan(2, 1) // a demo learner: this browser has no token for them
  const sent = fetch.mock.calls.map(([, init]) => init?.headers as Record<string, string>)
  expect(sent[0].Authorization).toBe("Bearer secret-7")
  expect(sent[1].Authorization).toBeUndefined()
})

it("forgets a learner the server says no longer exists", async () => {
  stubFetch({ learner_id: 9, seeded_terms: 0, token: "secret-9" })
  await api.createLearner("Gone", {}, "letmein")

  stubFetch({ detail: "learner not found" }, 404)
  await expect(api.plan(9, 1)).rejects.toThrow("removed from this browser")
  expect(myLearners().map((l) => l.id)).not.toContain(9)
})

it("shows FastAPI's error detail, not raw JSON", async () => {
  stubFetch({ detail: "That invite code isn't right." }, 403)
  await expect(api.createLearner("x", {}, "nope")).rejects.toThrow("That invite code isn't right. (POST /learners: 403)")
})
