import { useEffect, useMemo, useRef, useState } from "react"
import { api, captionsUrl, mediaUrl, type Learner, type PlanItem, type Video } from "@/api"
import { buildStops, crossed, MAX_PAUSES, type Stop } from "@/plan"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

type Mode = "study" | "glance"
const GLANCE_MS = 8000

export function Player({ learner, video, plan, onDone }: {
  learner: Learner
  video: Video
  plan: PlanItem[]
  onDone: (queued: PlanItem[]) => void
}) {
  const ref = useRef<HTMLVideoElement>(null)
  const fired = useRef(new Set<number>())
  const [mode, setMode] = useState<Mode>("study")
  const [card, setCard] = useState<Stop | null>(null)
  const [error, setError] = useState("")
  const { stops, queued } = useMemo(() => buildStops(plan, mode === "study" ? MAX_PAUSES : Infinity), [plan, mode])

  useEffect(() => {
    const v = ref.current!
    let prev = v.currentTime
    let raf = 0
    const onSeek = () => {
      prev = v.currentTime // a seek, not playback: never fire the stops it jumps over
    }
    const check = () => {
      const now = v.currentTime
      if (v.seeking) return onSeek()
      const stop = crossed(stops, fired.current, prev, now)
      prev = now
      if (stop) {
        fired.current.add(stop.ts)
        if (mode === "study") v.pause()
        setCard(stop)
        for (const item of stop.items)
          api
            .event({ learner_id: learner.id, video_id: video.id, type: mode === "study" ? "pause" : "glance",
                     term_id: item.term_id, ts: stop.ts })
            .catch(console.error) // logging must never stop the lecture; failures show in the console
        if (mode === "glance") setTimeout(() => setCard((c) => (c === stop ? null : c)), GLANCE_MS)
      }
    }
    const tick = () => {
      check() // every frame, so a visible player pauses within ~16 ms of the sentence end
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    // hidden windows throttle frames to ~2/s or stop them; timeupdate (~4/s) keeps checking there
    v.addEventListener("timeupdate", check)
    v.addEventListener("seeking", onSeek)
    return () => {
      cancelAnimationFrame(raf)
      v.removeEventListener("timeupdate", check)
      v.removeEventListener("seeking", onSeek)
    }
  }, [stops, mode, learner.id, video.id])

  function resume() {
    setCard(null)
    ref.current?.play()
  }

  function known(item: PlanItem) {
    if (!card) return
    api
      .known(learner.id, video.id, item.term_id, card.ts)
      .then(() => {
        const rest = card.items.filter((i) => i !== item)
        if (rest.length) setCard({ ...card, items: rest })
        else resume()
      })
      .catch((e) => setError(String(e)))
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div>
        <video ref={ref} src={mediaUrl(video.id)} controls preload="metadata"
               className="w-full rounded-lg bg-black" onEnded={() => onDone(queued)}>
          <track kind="captions" src={captionsUrl(video.id)} srcLang="en" label="English" />
        </video>
        <p className="mt-2 text-sm text-muted-foreground">
          {video.title} · {video.source} · {video.licence}
        </p>
      </div>
      <aside className="space-y-4">
        <div role="group" aria-label="Mode" className="flex flex-wrap gap-2">
          {(["study", "glance"] as const).map((m) => (
            <Button key={m} variant={mode === m ? "default" : "outline"} aria-pressed={mode === m}
                    onClick={() => setMode(m)}>
              {m === "study" ? "Study: pause for new terms" : "Glance: cards only"}
            </Button>
          ))}
        </div>
        <p className="text-sm text-muted-foreground">
          {stops.length} {mode === "study" ? "pauses" : "cards"} for {learner.name}
          {queued.length > 0 && `, ${queued.length} more terms saved for the end`}
        </p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {card && (
          <Card role="region" aria-live="polite" aria-label="New terms">
            <CardContent className="space-y-4">
              {card.items.map((item) => (
                <div key={item.term_id} className="space-y-1">
                  <h3 className="font-semibold">{item.term}</h3>
                  <p className="text-sm">{item.explanation}</p>
                  <Button variant="ghost" size="sm" onClick={() => known(item)}>I already know this</Button>
                </div>
              ))}
              {mode === "study" && <Button autoFocus onClick={resume}>Continue</Button>}
            </CardContent>
          </Card>
        )}
        <Button variant="outline" onClick={() => onDone(queued)}>Finish and take the quiz</Button>
      </aside>
    </section>
  )
}
