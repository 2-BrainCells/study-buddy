import { useEffect, useMemo, useRef, useState } from "react"
import { api, captionsUrl, mediaUrl, type Learner, type PlanItem, type Video } from "@/api"
import {
  buildStops, comfortableWith, crossed, fmtTime, initials, MAX_PAUSES, reasonText, type Stop,
} from "@/plan"
import { ChevronDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Mode = "study" | "glance"
const GLANCE_MS = 8000
const SESSION_ROWS = 8 // rows shown before "Show all", when the list is longer than SESSION_ROWS + 2
const SEEK_LEAD = 6 // seconds before a stop when jumping to it from the list, so the sentence plays first
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
  const bandRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLElement>(null)
  const continueRef = useRef<HTMLButtonElement>(null)
  const stickyRef = useRef<HTMLDivElement>(null)
  const fired = useRef(new Set<number>())
  const [seen, setSeen] = useState<number[]>([]) // fired stops, mirrored into state for the session list
  const [markedKnown, setMarkedKnown] = useState<number[]>([]) // "I already know this" clicks this session
  const [mode, setMode] = useState<Mode>("study")
  const [card, setCard] = useState<Stop | null>(null)
  const [now, setNow] = useState(0)
  const [error, setError] = useState("")
  const [showAll, setShowAll] = useState(false)

  // a click on "I already know this" moves the term to the skipped list and stops it pausing again
  const live = useMemo(
    () =>
      plan.map((p) =>
        markedKnown.includes(p.term_id) ? { ...p, status: "known" as const, reason: "you marked it known" } : p,
      ),
    [plan, markedKnown],
  )
  const { stops, queued } = useMemo(() => buildStops(live, mode === "study" ? MAX_PAUSES : Infinity), [live, mode])
  const skipped = live.filter((p) => p.status === "known")

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
        setSeen([...fired.current])
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
        setMarkedKnown((ids) => [...ids, item.term_id])
        const rest = card.items.filter((i) => i !== item)
        if (rest.length) setCard({ ...card, items: rest })
        else resume()
      })
      .catch((e) => setError(String(e)))
  }

  function jumpTo(ts: number) {
    const v = ref.current!
    fired.current.delete(ts) // replaying a moment from the list may pause there again
    v.currentTime = Math.max(0, ts - SEEK_LEAD)
    v.play()
    bandRef.current?.scrollIntoView({ block: "start", behavior: "smooth" })
  }

  const noun = mode === "study" ? "pauses" : "cards"
  const topics = comfortableWith(learner.questionnaire)
  const sessionRows = [
    ...stops.map((s) => ({
      ts: s.ts, terms: s.items.map((i) => i.term), kind: (seen.includes(s.ts) ? "seen" : "pause") as ChipKind,
    })),
    ...queued.map((q) => ({ ts: q.pause_ts, terms: [q.term], kind: "saved" as ChipKind })),
  ].sort((a, b) => a.ts - b.ts)

  return (
    <>
      {/* profile strip: whose lecture this is, and what the app knows about them */}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-5">
        <span aria-hidden className="grid size-11 place-items-center rounded-full bg-secondary text-sm font-semibold">
          {initials(learner.name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-serif text-xl font-semibold">{learner.name}</p>
          <p className="text-sm text-muted-foreground">
            {topics ? `Comfortable with ${topics}` : "No topics ticked in the questionnaire"}
            {" · "}
            {learner.note_terms ? `${learner.note_terms} terms from notes` : "no notes yet"}
          </p>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <Stat label={noun} value={stops.length} dot="bg-pause ring-1 ring-pause-ink" />
          <Stat label="skipped" value={skipped.length} dot="bg-known" />
          <Stat label="saved for end" value={queued.length} dot="bg-muted-foreground" />
        </dl>
      </div>

      {/* the lecture band: dark like a screen, so the video holds attention */}
      <div ref={bandRef} className="dark-zone bg-background text-foreground">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-x-8 gap-y-5 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_26rem]">
          {/* "contents" on a phone makes the sticky block a direct child of the band grid, so it stays stuck
              while the card scrolls under it; a normal column on desktop */}
          <div className="contents lg:block">
            <div ref={stickyRef} className="sticky top-0 z-10 -mx-4 bg-background px-4 pt-2 pb-3 lg:static lg:mx-0 lg:p-0">
              <p className="mb-2 text-xs text-muted-foreground lg:hidden">
                <span className="font-medium text-foreground">{learner.name}</span> · {stops.length} {noun} ·{" "}
                {queued.length} saved · {skipped.length} skipped
              </p>
              <video ref={ref} src={mediaUrl(video.id)} controls preload="metadata"
                     className="aspect-video w-full rounded-lg border bg-black" onEnded={() => onDone(queued)}>
                <track kind="captions" src={captionsUrl(video.id)} srcLang="en" label="English" />
              </video>
              <PauseTimeline stops={stops} queued={queued} skipped={skipped} active={card?.ts}
                             duration={video.duration_s} now={now} />
              <p className="mt-1 line-clamp-1 text-[11px] text-muted-foreground lg:mt-3 lg:line-clamp-2 lg:text-xs">
                {/* licence first so the CC BY-NC-SA attribution is never the part that gets cut */}
                {video.licence} · {video.title} · {video.source}
              </p>
            </div>
          </div>

          <aside className="lg:relative">
            <div className="flex flex-col gap-4 lg:absolute lg:inset-0">
            <div className="flex flex-wrap items-center gap-3">
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
              <p className="text-xs text-muted-foreground">{MODES.find((m) => m.id === mode)!.hint}</p>
            </div>

            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

            {card ? (
              <section ref={cardRef} aria-live="polite" aria-label="New terms"
                       className={cn(
                         "light-zone order-first rounded-lg border bg-card px-5 pt-5 text-card-foreground shadow-sm",
                         "[scrollbar-color:var(--input)_transparent] [scrollbar-width:thin]",
                         "lg:order-none lg:min-h-0 lg:flex-1 lg:overflow-auto",
                         mode === "glance" && "pb-5",
                       )}>
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span aria-hidden className="size-2 rounded-full bg-pause ring-1 ring-pause-ink" />
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
                      <span className="ml-2">{reasonText(item.reason)}</span>
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
            ) : (
              <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
                <p className="font-medium text-foreground">
                  {stops.length} {noun} planned for {learner.name}
                </p>
                <p className="mt-1">
                  {mode === "study"
                    ? "The lecture stops at the end of the sentence that introduces each new term, and a card appears here."
                    : "Cards appear here as new terms come up; the lecture keeps playing."}
                </p>
              </div>
            )}

            <Button variant="outline" className="min-h-11 shrink-0 self-start sm:min-h-9" onClick={() => onDone(queued)}>
              Finish and take the quiz
            </Button>
            </div>
          </aside>
        </div>
      </div>

      {/* below the band: the whole lecture for this learner, and what it skips for them */}
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-4 py-10 lg:grid-cols-2">
        <section aria-labelledby="session-title">
          <h2 id="session-title" className="font-serif text-xl font-semibold">This lecture for {learner.name}</h2>
          <p className="mt-1 text-sm text-muted-foreground">Every moment with a new term. Select one to jump there.</p>
          <ol className="mt-4 divide-y rounded-lg border bg-card">
            {(showAll || sessionRows.length <= SESSION_ROWS + 2 ? sessionRows : sessionRows.slice(0, SESSION_ROWS)).map((r) => (
              <li key={`${r.kind}-${r.ts}-${r.terms[0]}`}>
                <button type="button" onClick={() => jumpTo(r.ts)}
                        className="flex min-h-12 w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 ease-calm hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2">
                  <span className="w-11 shrink-0 text-sm text-muted-foreground">{fmtTime(r.ts)}</span>
                  <span className="min-w-0 flex-1 text-sm font-medium">{r.terms.join(" · ")}</span>
                  <StateChip kind={r.kind} noun={mode === "study" ? "Pause" : "Card"} />
                </button>
              </li>
            ))}
          </ol>
          {sessionRows.length > SESSION_ROWS + 2 && (
            <button type="button" onClick={() => setShowAll((v) => !v)}
                    className="mt-3 min-h-11 rounded-md text-sm font-medium text-pause-ink underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 sm:min-h-8">
              {showAll ? "Show fewer" : `Show all ${sessionRows.length}`}
            </button>
          )}
        </section>

        <section aria-labelledby="skipped-title">
          <h2 id="skipped-title" className="font-serif text-xl font-semibold">Skipped for {learner.name}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {skipped.length
              ? "Already known, so the lecture doesn't stop for these."
              : "Nothing skipped yet: everything in this lecture is new for this learner."}
          </p>
          {skipped.length > 0 && (
            <ul className="mt-4 divide-y rounded-lg border bg-card">
              {skipped.map((p) => (
                <li key={p.term_id}>
                  <details className="group">
                    <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-4 py-3 hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2">
                      <span className="w-11 shrink-0 text-sm text-muted-foreground">{fmtTime(p.pause_ts)}</span>
                      <span className="min-w-0 flex-1 text-sm font-medium">{p.term}</span>
                      <span className="flex shrink-0 items-center gap-1.5 text-xs text-known">
                        <span aria-hidden className="size-2 rounded-full bg-known" />
                        {reasonText(p.reason)}
                      </span>
                      <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground transition-transform duration-150 ease-calm group-open:rotate-180" />
                    </summary>
                    <p className="px-4 pb-3 pl-18 font-serif leading-relaxed text-foreground/90">{p.explanation}</p>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  )
}

type ChipKind = "seen" | "pause" | "saved"

function Stat({ label, value, dot }: { label: string; value: number; dot: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden className={cn("size-2 rounded-full", dot)} />
      <dt className="sr-only">{label}</dt>
      <dd>
        <span className="font-semibold">{value}</span> <span className="text-muted-foreground">{label}</span>
      </dd>
    </div>
  )
}

function StateChip({ kind, noun }: { kind: ChipKind; noun: string }) {
  const style = {
    pause: { dot: "bg-pause ring-1 ring-pause-ink", text: noun },
    seen: { dot: "ring-1 ring-pause-ink ring-inset", text: "Seen" },
    saved: { dot: "bg-muted-foreground", text: "Saved for end" },
  }[kind]
  return (
    <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
      <span aria-hidden className={cn("size-2 rounded-full", style.dot)} />
      {style.text}
    </span>
  )
}

/** A slim track under the video: amber ticks where this learner pauses, grey for saved, teal for skipped. */
function PauseTimeline({ stops, queued, skipped, active, duration, now }: {
  stops: Stop[]
  queued: PlanItem[]
  skipped: PlanItem[]
  active?: number
  duration: number
  now: number
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
      <div role="img"
           aria-label={`Pauses at ${stops.map((s) => fmtTime(s.ts)).join(", ")}; ${queued.length} saved for the end; ${skipped.length} skipped`}
           className="relative h-1 rounded-full bg-input">
        <div className="absolute inset-y-0 left-0 rounded-full bg-foreground/75" style={{ width: pct(now) }} />
        {skipped.map((p) => (
          <span key={`k${p.term_id}`} className="absolute top-1/2 h-2 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-known"
                style={{ left: pct(p.pause_ts) }} />
        ))}
        {queued.map((q) => (
          <span key={`q${q.term_id}`} className="absolute top-1/2 h-2 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-muted-foreground"
                style={{ left: pct(q.pause_ts) }} />
        ))}
        {clusters.map((c) => (
          <span key={c[0].ts}
                className={cn("absolute top-1/2 z-10 h-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-pause",
                              c.length > 1 ? "w-2" : "w-1", c.some((s) => s.ts === active) && "ring-4 ring-pause/30")}
                style={{ left: pct((c[0].ts + c.at(-1)!.ts) / 2) }} />
        ))}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground max-lg:hidden">
        <Legend dot="bg-pause" text="pauses" />
        <Legend dot="bg-muted-foreground" text="saved for the end" />
        <Legend dot="bg-known" text="skipped, already known" />
      </p>
    </div>
  )
}

function Legend({ dot, text }: { dot: string; text: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span aria-hidden className={cn("size-1.5 rounded-full", dot)} />
      {text}
    </span>
  )
}
