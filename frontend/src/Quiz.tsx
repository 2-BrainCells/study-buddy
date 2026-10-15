import { useEffect, useState } from "react"
import { api, type Learner, type PlanItem, type Question, type Video } from "@/api"
import { pickQuiz } from "@/plan"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

export function Quiz({ learner, video, plan, queued, onBack }: {
  learner: Learner
  video: Video
  plan: PlanItem[]
  queued: PlanItem[]
  onBack: () => void
}) {
  const [qs, setQs] = useState<Question[] | null>(null)
  const [i, setI] = useState(0)
  const [picked, setPicked] = useState<number | null>(null)
  const [score, setScore] = useState(0)
  const [error, setError] = useState("")

  useEffect(() => {
    api.quiz(video.id).then((all) => setQs(pickQuiz(all, plan))).catch((e) => setError(String(e)))
  }, [video.id, plan])

  function choose(k: number) {
    if (picked !== null || !qs) return
    const q = qs[i]
    const correct = k === q.answer
    setPicked(k)
    if (correct) setScore((s) => s + 1)
    api
      .event({ learner_id: learner.id, video_id: video.id, type: "quiz_answer", term_id: q.term_id, correct })
      .catch(console.error) // the score still counts; failures show in the console
  }

  function next() {
    setPicked(null)
    setI((n) => n + 1)
  }

  const q = qs?.[i]
  return (
    <section className="mx-auto max-w-2xl space-y-8">
      <h2 className="font-serif text-3xl font-semibold">{learner.name}'s quiz</h2>
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {!qs && !error && <p role="status">Loading quiz…</p>}
      {qs && q && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Question {i + 1} of {qs.length}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="font-serif text-2xl leading-snug font-semibold">{q.question}</p>
            <div className="grid gap-2">
              {q.options.map((o, k) => (
                <button key={k} type="button" onClick={() => choose(k)} aria-pressed={picked === k}
                        className={cn(
                          "min-h-12 w-full rounded-md border bg-card px-4 py-3 text-left text-sm transition-colors duration-150 ease-calm",
                          "focus-visible:outline-2 focus-visible:outline-offset-2",
                          picked === null && "hover:border-pause-ink",
                          picked !== null && k === q.answer && "border-known bg-known/10",
                          picked === k && k !== q.answer && "border-destructive bg-destructive/10",
                        )}>
                  {o}
                  {picked !== null && k === q.answer && <span className="font-medium text-known"> (correct answer)</span>}
                  {picked === k && k !== q.answer && <span className="font-medium text-destructive"> (your answer, wrong)</span>}
                </button>
              ))}
            </div>
            {picked !== null && <Button autoFocus onClick={next}>Next</Button>}
          </CardContent>
        </Card>
      )}
      {qs && i === qs.length && (
        <div className="space-y-3">
          <p className="text-lg font-semibold">Score {score}/{qs.length}</p>
          <Button onClick={onBack}>Back</Button>
        </div>
      )}
      {queued.length > 0 && (
        <details className="group rounded-lg border bg-card px-5 py-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium">
            <span aria-hidden className="size-2 rounded-full bg-muted-foreground" />
            {queued.length} terms we didn't stop for
            <ChevronDown aria-hidden className="ml-auto size-4 text-muted-foreground transition-transform duration-150 ease-calm group-open:rotate-180" />
          </summary>
          <div className="mt-4 space-y-4">
            {queued.map((p) => (
              <div key={p.term_id}>
                <h3 className="font-serif text-lg font-semibold">{p.term}</h3>
                <p className="mt-1 font-serif leading-relaxed text-foreground/90">{p.explanation}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  )
}
