import { useEffect, useState } from "react"
import { api, type Learner, type Video } from "@/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

const TOPICS = [
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
    Object.fromEntries(TOPICS.map(([k]) => [k, false])),
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
    <section className="grid gap-8 lg:grid-cols-2">
      <div className="space-y-4">
        <h2 className="text-lg font-semibold">Watch as</h2>
        {!video && <p className="text-muted-foreground">No processed video yet.</p>}
        {video && (
          <>
            <p className="text-sm text-muted-foreground">{video.title}</p>
            <div className="flex flex-wrap gap-2">
              {learners.map((l) => (
                <Button key={l.id} onClick={() => onStart(l, video)}>{l.name}</Button>
              ))}
            </div>
          </>
        )}
        {msg && <p role="status" className="text-sm">{msg}</p>}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>New learner</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); create() }}>
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">I'm comfortable with</legend>
              {TOPICS.map(([k, label]) => (
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
            <Button type="submit" disabled={busy}>{busy ? "Working…" : "Create learner"}</Button>
          </form>
        </CardContent>
      </Card>
    </section>
  )
}
