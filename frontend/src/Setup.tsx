import { useEffect, useState } from "react"
import { api, type Learner, type Video } from "@/api"
import { comfortableWith, initials } from "@/plan"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

const QUESTIONS = [
  ["calculus", "Calculus (derivatives, chain rule)"],
  ["linear_algebra", "Linear algebra (vectors, matrices)"],
  ["probability", "Probability (random variables, expected value)"],
  ["ml_basics", "ML basics (linear regression, gradient descent)"],
  ["python", "Python and NumPy"],
] as const

export function Setup({ onStart, error }: { onStart: (l: Learner, v: Video) => void; error: string }) {
  const [learners, setLearners] = useState<Learner[]>([])
  const [video, setVideo] = useState<Video | null>(null)
  const [msg, setMsg] = useState(error)
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState("")
  const [answers, setAnswers] = useState<Record<string, boolean>>(
    Object.fromEntries(QUESTIONS.map(([k]) => [k, false])),
  )
  const [notes, setNotes] = useState("")

  function load() {
    Promise.all([api.learners(), api.videos()])
      .then(([l, v]) => {
        setLearners(l)
        setVideo(v[0] ?? null) // ponytail: one video for now; add a picker when there's a second
      })
      .catch((e) => setMsg(String(e)))
  }
  useEffect(load, [])

  async function create() {
    setBusy(true)
    try {
      const { learner_id, seeded_terms } = await api.createLearner(name, answers)
      let m = `Created ${name} with ${seeded_terms} terms from the questionnaire.`
      if (notes.trim()) {
        setMsg(`${m} Indexing notes…`)
        const { terms_added } = await api.addNotes(learner_id, notes)
        m += ` Indexed ${terms_added} terms from the notes; preparing the plan in the background (about 2–4 min).`
      }
      setMsg(m)
      setName("")
      setNotes("")
      load()
    } catch (e) {
      setMsg(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div>
        <h2 className="font-serif text-3xl leading-tight font-semibold text-balance sm:text-4xl">
          The lecture pauses where <em>you</em> need it.
        </h2>
        <p className="mt-3 max-w-[60ch] text-muted-foreground">
          Study Buddy reads a learner's notes and questionnaire, then stops the lecture only at terms that are new
          to them, explains each one in plain English, and ends with a short quiz. Two learners, one lecture,
          two different experiences.
        </p>

        <h3 className="mt-10 text-sm font-medium">Watch {video ? video.title : "a lecture"} as</h3>
        {!video && <p className="mt-2 text-muted-foreground">No processed video yet.</p>}
        {video && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {learners.map((l) => {
              const topics = comfortableWith(l.questionnaire)
              return (
                <button key={l.id} type="button" onClick={() => onStart(l, video)}
                        className="group flex items-start gap-3 rounded-lg border bg-card p-4 text-left transition-colors duration-150 ease-calm hover:border-primary focus-visible:outline-2 focus-visible:outline-offset-2">
                  <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary text-sm font-semibold">
                    {initials(l.name)}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-serif text-lg font-semibold">{l.name}</span>
                    <span className="block text-sm text-muted-foreground">
                      {topics ? `Comfortable with ${topics}` : "A beginner: no topics ticked"}
                    </span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {l.note_terms ? `${l.note_terms} terms from notes` : "No notes yet"}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        )}
        {msg && <p role="status" className="mt-4 text-sm">{msg}</p>}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-xl font-semibold">Add a learner</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create() }}>
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">I'm comfortable with</legend>
              {QUESTIONS.map(([k, label]) => (
                <div key={k} className="flex items-center gap-2">
                  <input id={k} type="checkbox" className="size-4 accent-primary" checked={answers[k]}
                         onChange={(e) => setAnswers({ ...answers, [k]: e.target.checked })} />
                  <Label htmlFor={k} className="font-normal">{label}</Label>
                </div>
              ))}
            </fieldset>
            <div className="space-y-2">
              <Label htmlFor="notes">Your notes (Markdown, optional)</Label>
              <Textarea id="notes" rows={8} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <Button type="submit" variant="secondary" disabled={busy}>{busy ? "Working…" : "Create learner"}</Button>
          </form>
        </CardContent>
      </Card>
    </section>
  )
}
