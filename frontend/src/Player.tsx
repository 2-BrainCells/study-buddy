import { useEffect, useMemo, useRef, useState } from "react"
import { api, captionsUrl, mediaUrl, type Learner, type PlanItem, type Video } from "@/api"
import { buildStops, crossed, fmtTime, MAX_PAUSES, whyText, type Stop } from "@/plan"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Mode = "study" | "glance"
const GLANCE_MS = 8000
const MODES = [
  { id: "study", label: "Study", hint: "Pauses for new terms" },
  { id: "glance", label: "Glance", hint: "Cards, no pauses" },
] as const

export function Player({ learner, video, plan, onDone }: {
  learner: Learner
  video: Video
  plan: PlanItem[]
  onDone: (queued: PlanItem[]) => void
}) {
  const ref = useRef<HTMLVideoElement>(null)
  const cardRef = useRef<HTMLElement>(null)
  const continueRef = useRef<HTMLButtonElement>(null)
  const stickyRef = useRef<HTMLDivElement>(null)
  const fired = useRef(new Set<number>())
  const [mode, setMode] = useState<Mode>("study")
  const [card, setCard] = useState<Stop | null>(null)
  const [now, setNow] = useState(0)
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
      const t = v.currentTime
      if (v.seeking) return onSeek()
      const stop = crossed(stops, fired.current, prev, t)
      prev = t
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
    const onTime = () => {
      check() // hidden windows throttle frames to ~2/s or stop them; timeupdate (~4/s) keeps checking there
      setNow(v.currentTime)
    }
    const onPlay = () => {
      if (mode === "study") setCard(null) // the video's own play button counts as Continue
    }
    raf = requestAnimationFrame(tick)
    v.addEventListener("timeupdate", onTime)
    v.addEventListener("seeking", onSeek)
    v.addEventListener("play", onPlay)
    return () => {
      cancelAnimationFrame(raf)
      v.removeEventListener("timeupdate", onTime)
      v.removeEventListener("seeking", onSeek)
      v.removeEventListener("play", onPlay)
    }
  }, [stops, mode, learner.id, video.id])

  useEffect(() => {
    if (!card || mode !== "study") return
    // focus Continue without letting the browser scroll it into view (that clipped the video on short screens)
    continueRef.current?.focus({ preventScroll: true })
    // on a phone the card sits under the sticky video block: scroll so its top lands just below that block
    if (matchMedia("(max-width: 1023px)").matches && cardRef.current && stickyRef.current) {
      const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches
      const top = cardRef.current.getBoundingClientRect().top + scrollY - stickyRef.current.offsetHeight - 12
      scrollTo({ top, behavior: reduce ? "auto" : "smooth" })
    }
  }, [card, mode])

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

  const noun = mode === "study" ? "pauses" : "cards"
  return (
    <section className="grid grid-cols-1 gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1fr)_28rem]">
      {/* "contents" on a phone makes the sticky block a direct child of the whole player, so it stays stuck
          while the card scrolls under it; a normal column on desktop */}
      <div className="contents lg:block">
        <div ref={stickyRef} className="sticky top-0 z-10 -mx-4 bg-background px-4 pt-2 pb-3 lg:static lg:mx-0 lg:p-0">
          <video ref={ref} src={mediaUrl(video.id)} controls preload="metadata"
                 className="aspect-video w-full rounded-lg border bg-black" onEnded={() => onDone(queued)}>
            <track kind="captions" src={captionsUrl(video.id)} srcLang="en" label="English" />
          </video>
          <PauseTimeline stops={stops} queued={queued} active={card?.ts} duration={video.duration_s} now={now}
                         label={`${learner.name}'s ${stops.length} ${noun}`} />
          <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground lg:mt-4 lg:text-xs">
            {/* licence first so the CC BY-NC-SA attribution is never the part that gets cut */}
            {video.licence} · {video.title} · {video.source}
          </p>
        </div>
      </div>

      <aside className="flex flex-col gap-5 lg:sticky lg:top-6 lg:max-h-[calc(100dvh-7rem)] lg:self-start">
        <div>
          <div role="group" aria-label="Mode" className="inline-flex rounded-lg border bg-card p-0.5">
            {MODES.map((m) => (
              <button key={m.id} type="button" aria-pressed={mode === m.id} onClick={() => setMode(m.id)}
                      className={cn(
                        "min-h-11 rounded-md px-4 text-sm font-medium transition-colors duration-150 ease-calm sm:min-h-8",
                        "focus-visible:outline-2 focus-visible:outline-offset-2",
                        mode === m.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                      )}>
                {m.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{MODES.find((m) => m.id === mode)!.hint}</p>
        </div>

        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{stops.length} {noun}</span> for {learner.name}
          {queued.length > 0 && ` · ${queued.length} saved for the end`}
        </p>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

        {card && (
          <section ref={cardRef} aria-live="polite" aria-label="New terms"
                   className={cn(
                     "order-first rounded-lg border bg-card px-5 pt-5 [scrollbar-color:var(--input)_transparent] [scrollbar-width:thin]",
                     "lg:order-none lg:min-h-0 lg:flex-1 lg:overflow-auto",
                     mode === "glance" && "pb-5",
                   )}>
            <p className="text-xs text-muted-foreground">
              {fmtTime(card.ts)} · {card.items.length > 1 ? `${card.items.length} new terms` : "new for you"}
            </p>
            {card.items.map((item) => (
              <div key={item.term_id} className="mt-3 border-t pt-4 first-of-type:border-t-0 first-of-type:pt-0">
                <h3 className="font-serif text-xl leading-snug font-semibold">{item.term}</h3>
                <p className="mt-2 font-serif text-[1.0625rem] leading-relaxed text-foreground/90">{item.explanation}</p>
                <p className="mt-3 text-sm text-muted-foreground">
                  <span className="text-[0.6875rem] font-medium tracking-wider uppercase">
                    {mode === "study" ? "Why it paused" : "Why it's shown"}
                  </span>
                  <span className="ml-2">{whyText(item.reason)}</span>
                </p>
                <Button variant="ghost" size="sm" className="mt-1 -ml-2.5 min-h-11 sm:min-h-7"
                        onClick={() => known(item)}>
                  I already know this
                </Button>
              </div>
            ))}
            {mode === "study" && (
              // stays visible at the bottom of a long card (two terms at one pause)
              <div className="sticky bottom-0 -mx-5 mt-3 border-t bg-card px-5 py-3">
                <Button ref={continueRef} onClick={resume} className="min-h-11 px-5 sm:min-h-9">Continue</Button>
              </div>
            )}
          </section>
        )}

        <Button variant="outline" className="min-h-11 shrink-0 self-start sm:min-h-9" onClick={() => onDone(queued)}>
          Finish and take the quiz
        </Button>
      </aside>
    </section>
  )
}

/** A slim track under the video: amber ticks where this learner pauses, grey ticks for terms saved for the end. */
function PauseTimeline({ stops, queued, active, duration, now, label }: {
  stops: Stop[]
  queued: PlanItem[]
  active?: number
  duration: number
  now: number
  label: string
}) {
  const pct = (s: number) => `${Math.min(100, (s / duration) * 100)}%`
  // stops closer than 1.5% of the track would overlap; draw each cluster as one wider tick
  const clusters: Stop[][] = []
  for (const s of stops) {
    const last = clusters.at(-1)
    if (last && (s.ts - last.at(-1)!.ts) / duration < 0.015) last.push(s)
    else clusters.push([s])
  }
  return (
    <div className="mt-3">
      <div role="img" aria-label={`${label} at ${stops.map((s) => fmtTime(s.ts)).join(", ")}`}
           className="relative h-1 rounded-full bg-input">
        <div className="absolute inset-y-0 left-0 rounded-full bg-foreground/75" style={{ width: pct(now) }} />
        {queued.map((q) => (
          <span key={q.term_id} className="absolute top-1/2 h-2 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-muted-foreground"
                style={{ left: pct(q.pause_ts) }} />
        ))}
        {clusters.map((c) => (
          <span key={c[0].ts}
                className={cn("absolute top-1/2 z-10 h-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary",
                              c.length > 1 ? "w-2" : "w-1", c.some((s) => s.ts === active) && "ring-4 ring-primary/30")}
                style={{ left: pct((c[0].ts + c.at(-1)!.ts) / 2) }} />
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {label}
        {queued.length > 0 && <> · <span className="text-foreground/70">grey</span>: saved for the end</>}
      </p>
    </div>
  )
}
