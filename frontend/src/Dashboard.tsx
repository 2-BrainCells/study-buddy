import { useEffect, useState } from "react"
import { api, type Dashboard as DashboardData, type DashTerm, type StageUsage, type Usage, type Video } from "@/api"
import { fmtTime } from "@/plan"
import { cn } from "@/lib/utils"

const usd = (x: number | null | undefined, digits = 4) => (x == null ? "n/a" : `$${x.toFixed(digits)}`)
const num = (x: number) => x.toLocaleString("en-US")
const STAGES: Record<string, string> = {
  terms: "Find terms and quiz",
  terms_repair: "Repair a reply",
  notes_terms: "Read learner notes",
  novelty: "Novelty check",
  transcribe: "Transcribe (CPU)",
  embed: "Embed terms (CPU)",
  check: "Endpoint check",
}
const PER_CALL: Record<string, string> = {
  terms: "1 call per ~600-word chunk of transcript",
  terms_repair: "1 retry when a reply breaks the schema",
  notes_terms: "1 call per ~600 words of notes",
  novelty: "1 call checks all of a learner’s open terms; runs in the background",
  transcribe: "1 run transcribes the whole clip",
  embed: "1 run embeds every term",
}
const isCpu = (s: StageUsage) => s.cost_usd == null // no Token Factory price: runs on our CPU

/** Ed-tech dashboard (where learners struggle) and the AMD usage panel, from real events and stage_costs only. */
export function Dashboard({ video }: { video: Video }) {
  const [dash, setDash] = useState<DashboardData | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    Promise.all([api.dashboard(video.id), api.usage()])
      .then(([d, u]) => {
        setDash(d)
        setUsage(u)
      })
      .catch((e) => setError(String(e)))
  }, [video.id])

  if (error) return <p role="alert" className="text-destructive">{error}</p>
  if (!dash || !usage) return <p role="status" className="text-muted-foreground">Loading the dashboard…</p>

  const accuracy = dash.quiz_answered ? Math.round((100 * dash.quiz_correct) / dash.quiz_answered) : null
  const perLearner = usage.learners.length
    ? usage.learners.reduce((s, l) => s + l.cost_usd, 0) / usage.learners.length
    : null
  const tf = usage.stages.filter((s) => !isCpu(s)).sort((a, b) => (b.cost_usd ?? 0) - (a.cost_usd ?? 0))
  const tfRequests = tf.reduce((s, x) => s + x.requests, 0)
  const active = dash.terms.filter((t) => t.score > 0 || t.marked_known > 0)
  const shown = showAll ? dash.terms : active
  const q = usage.quota

  return (
    <div className="space-y-12">
      <header>
        <h2 className="font-serif text-3xl font-semibold">{video.title}</h2>
        <p className="mt-1 text-muted-foreground">For the ed-tech team: how learners did, and what the AMD models cost.</p>
      </header>

      {/* at a glance: both halves of the story above the fold */}
      <section aria-label="At a glance" className="grid gap-x-6 gap-y-4 xl:grid-cols-[2fr_4fr]">
        <div>
          <p className="mb-2 text-xs font-medium tracking-wider text-muted-foreground uppercase">Learners</p>
          <div className="grid auto-rows-fr grid-cols-2 gap-3">
            <Tile label="Pauses taken" value={num(dash.pauses)} note={`${dash.sessions} of ${dash.learners} learners watched`} />
            <Tile label="Quiz accuracy" value={accuracy == null ? "n/a" : `${accuracy}%`}
                  note={dash.quiz_answered ? `${dash.quiz_correct} of ${dash.quiz_answered} right` : "no answers yet"} />
          </div>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium tracking-wider text-muted-foreground uppercase">AMD Token Factory</p>
          <div className="grid auto-rows-fr grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Per lecture hour" value={usd(usage.lecture?.cost_per_hour_usd)} note="once per video" />
            <Tile label="Per learner" value={usd(perLearner)} note="notes + novelty" />
            <Tile label="Requests" value={num(tfRequests)} note={`${usage.totals.retries_429} hit the rate limit`} />
            <BudgetTile usage={usage} />
          </div>
        </div>
      </section>

      <section aria-labelledby="struggle-title" className="space-y-5">
        <h3 id="struggle-title" className="font-serif text-2xl font-semibold">Where learners struggle</h3>
        <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
        <LectureStrip terms={dash.terms} duration={video.duration_s} />
        <p className="text-sm text-muted-foreground">
          {dash.sessions === 0
            ? "No sessions yet: this fills in as learners watch the lecture."
            : `${dash.sessions} learner${dash.sessions === 1 ? "" : "s"}, ${dash.pauses} pause${dash.pauses === 1 ? "" : "s"} so far` +
              (active[0] ? `; most activity on “${active[0].term}” at ${fmtTime(active[0].pause_ts)}.` : ".")}
        </p>
        </div>
        <div>
        <TermTable terms={shown} learners={dash.learners}
                   caption={showAll ? `All ${dash.terms.length} terms, hardest first` : "Terms with activity, hardest first"} />
        <button type="button" onClick={() => setShowAll((v) => !v)}
                className="min-h-11 rounded-md text-sm font-medium text-pause-ink underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 sm:min-h-8">
          {showAll ? "Show only terms with activity" : `Show all ${dash.terms.length} terms`}
        </button>
        </div>
        </div>
      </section>

      <section aria-labelledby="usage-title" className="space-y-5">
        <div>
          <h3 id="usage-title" className="font-serif text-2xl font-semibold">AMD usage</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Every model call goes through AMD Token Factory (MiMo-V2.6-Flash). Transcription and embeddings run on CPU.
          </p>
        </div>
        <StageTable stages={[...tf, ...usage.stages.filter(isCpu)]} totalCost={usage.totals.cost_usd} />
        <p className="text-xs text-muted-foreground">
          Costs use the MiMo-V2.6-Flash list price ($0.14 / $0.28 per million input / output tokens), all runs to date.
          {q.available &&
            ` Token Factory's own bill for the last 24 hours was ${usd(q.last_24_hours.cost)} (${num(q.last_24_hours.requests)} requests),
              lower than list price because cached prompt tokens are cheaper.`}
        </p>
      </section>
    </div>
  )
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="h-full min-h-30 rounded-lg border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-serif text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 truncate text-xs text-muted-foreground" title={note}>{note}</p>
    </div>
  )
}

function BudgetTile({ usage }: { usage: Usage }) {
  const q = usage.quota
  if (!q.available) return <Tile label="Daily budget" value="n/a" note={`Not reported: ${q.reason}`} />
  const used = q.daily_used_usd ?? 0
  const limit = q.daily_limit_usd ?? 0
  const pct = limit ? Math.min(100, (100 * used) / limit) : 0
  const reset = q.reset_at ? new Date(q.reset_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "?"
  return (
    <div className="h-full min-h-30 rounded-lg border bg-card p-4">
      <p className="text-xs text-muted-foreground">Budget left today</p>
      <p className="mt-1 font-serif text-2xl font-semibold tabular-nums">{usd(q.daily_remaining_usd, 2)}</p>
      <div className="mt-2 h-1.5 rounded-full border border-input/60 bg-input/20" role="meter" aria-valuemin={0}
           aria-valuemax={limit} aria-valuenow={used} aria-label={`${usd(used)} of ${usd(limit, 2)} used today`}>
        <div className="h-full rounded-full bg-foreground/70" style={{ width: `max(2px, ${pct}%)` }} />
      </div>
      <p className="mt-1 truncate text-xs text-muted-foreground"
         title={`${usd(used)} of ${usd(limit, 2)} used since the ${reset} reset; ${q.rpm_limit ?? "?"} requests/min limit`}>
        {usd(used)} used today
      </p>
    </div>
  )
}

/** The lecture as a strip, like the player's timeline: a tick per term; taller and amber where learners paused. */
function LectureStrip({ terms, duration }: { terms: DashTerm[]; duration: number }) {
  const pct = (s: number) => `${Math.min(100, (s / duration) * 100)}%`
  const max = Math.max(1, ...terms.map((t) => t.score))
  const activeTs = new Set(terms.filter((t) => t.score).map((t) => t.pause_ts))
  const ticks = [...terms.filter((t) => !t.score && !activeTs.has(t.pause_ts)), ...terms.filter((t) => t.score)]
  return (
    <figure className="rounded-lg border bg-card p-5">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">The lecture, term by term</span>
        <span className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span aria-hidden className="size-2 rounded-full bg-pause ring-1 ring-pause-ink" />paused or got wrong (tallest: {max} {max === 1 ? "event" : "events"})</span>
          <span className="flex items-center gap-1.5"><span aria-hidden className="size-2 rounded-full bg-muted-foreground/40" />no trouble yet</span>
        </span>
      </figcaption>
      <div role="img" className="relative mt-6 h-16"
           aria-label={terms.filter((t) => t.score).map((t) => `${t.term} at ${fmtTime(t.pause_ts)}: ${t.paused} paused, ${t.wrong} wrong`).join("; ") || "No activity yet"}>
        <div className="absolute inset-x-0 bottom-0 h-px bg-input" />
        {ticks.map((t) => (
          <span key={t.term_id} title={`${t.term} · ${fmtTime(t.pause_ts)} · ${t.paused} paused · ${t.wrong} wrong`}
                className={cn("absolute bottom-0 w-1 -translate-x-1/2 rounded-t-full",
                              t.score ? "bg-pause ring-1 ring-pause-ink" : "bg-muted-foreground/40")}
                style={{ left: pct(t.pause_ts), height: t.score ? `${30 + 70 * (t.score / max)}%` : "18%" }} />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>0:00</span><span>{fmtTime(duration / 2)}</span><span>{fmtTime(duration)}</span>
      </div>
    </figure>
  )
}

function TermTable({ terms, learners, caption }: { terms: DashTerm[]; learners: number; caption: string }) {
  return (
    <>
    <div className="rounded-lg border bg-card md:hidden">
      <p className="px-4 pt-4 pb-2 text-sm font-medium">{caption}</p>
      <ul className="divide-y tabular-nums">
        {terms.length === 0 && <li className="px-4 py-3 text-sm text-muted-foreground">No activity yet.</li>}
        {terms.map((t) => (
          <li key={t.term_id} className="px-4 py-3">
            <p className="text-sm font-medium">
              {t.term} <span className="font-normal text-muted-foreground">{fmtTime(t.pause_ts)}</span>
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              new for {t.new_for} of {learners} · paused {t.paused} · knew it {t.marked_known} · quiz{" "}
              {t.answered ? `${t.wrong} of ${t.answered} wrong` : "–"}
            </p>
          </li>
        ))}
      </ul>
    </div>
    <div className="hidden overflow-x-auto rounded-lg border bg-card md:block">
      <table className="w-full text-sm">
        <caption className="px-4 pt-4 pb-2 text-left text-sm font-medium">{caption}</caption>
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b">
            <th scope="col" className="px-4 py-2 text-left font-medium">Term</th>
            <th scope="col" className="px-2 py-2 text-right font-medium whitespace-nowrap">New for</th>
            <th scope="col" className="px-2 py-2 text-right font-medium">Paused</th>
            <th scope="col" className="px-2 py-2 text-right font-medium whitespace-nowrap">Knew it</th>
            <th scope="col" className="px-4 py-2 text-right font-medium whitespace-nowrap">Quiz wrong</th>
          </tr>
        </thead>
        <tbody className="divide-y tabular-nums">
          {terms.length === 0 && (
            <tr><td colSpan={5} className="px-4 py-3 text-muted-foreground">No activity yet.</td></tr>
          )}
          {terms.map((t) => (
            <tr key={t.term_id}>
              <th scope="row" className="px-4 py-2 text-left font-medium">
                {t.term} <span className="font-normal text-muted-foreground">{fmtTime(t.pause_ts)}</span>
              </th>
              <td className="px-2 py-2 text-right whitespace-nowrap">{t.new_for} of {learners}</td>
              <td className="px-2 py-2 text-right">{t.paused}</td>
              <td className="px-2 py-2 text-right">{t.marked_known}</td>
              <td className="px-4 py-2 text-right whitespace-nowrap">{t.answered ? `${t.wrong} of ${t.answered}` : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
  )
}

function StageTable({ stages, totalCost }: { stages: StageUsage[]; totalCost: number }) {
  const maxTokens = Math.max(1, ...stages.map((s) => s.input_tokens + s.output_tokens))
  const totalCalls = stages.reduce((n, s) => n + s.requests, 0)
  const tfCalls = stages.filter((s) => !isCpu(s)).reduce((n, s) => n + s.requests, 0)
  const totalTokens = stages.reduce((n, s) => n + s.input_tokens + s.output_tokens, 0)
  return (
    <>
    {/* phone: one stacked row per stage, cost always visible */}
    <ul className="divide-y rounded-lg border bg-card md:hidden">
      {stages.map((s) => (
        <li key={`${s.stage}-${s.model}`} className="px-4 py-3 tabular-nums">
          <p className="flex justify-between gap-3 text-sm font-medium">
            <span>{STAGES[s.stage] ?? s.stage}</span>
            <span>{isCpu(s) ? "CPU" : usd(s.cost_usd)}</span>
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {num(s.requests)} {s.requests === 1 ? "call" : "calls"}
            {s.input_tokens + s.output_tokens ? ` · ${num(s.input_tokens + s.output_tokens)} tokens` : ""}
            {` · ${(s.avg_latency_ms / 1000).toFixed(1)} s each`}
          </p>
          {PER_CALL[s.stage] && <p className="text-xs text-muted-foreground">{PER_CALL[s.stage]}</p>}
        </li>
      ))}
      <li className="flex justify-between px-4 py-3 text-sm font-medium tabular-nums"><span>Total</span><span>{usd(totalCost)}</span></li>
    </ul>
    <div className="hidden overflow-x-auto rounded-lg border bg-card md:block">
      <table className="w-full text-sm">
        <caption className="px-4 pt-4 pb-2 text-left text-sm font-medium">Per pipeline stage, all runs to date</caption>
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b">
            <th scope="col" className="px-4 py-2 text-left font-medium">Stage</th>
            <th scope="col" className="px-2 py-2 text-right font-medium">Calls</th>
            <th scope="col" className="w-1/4 px-2 py-2 text-left font-medium">Tokens (in + out)</th>
            <th scope="col" className="px-2 py-2 text-right font-medium whitespace-nowrap">Avg time per call</th>
            <th scope="col" className="px-4 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y tabular-nums">
          {stages.map((s) => {
            const tokens = s.input_tokens + s.output_tokens
            return (
              <tr key={`${s.stage}-${s.model}`}>
                <th scope="row" className="px-4 py-2 text-left font-medium">
                  <span className="whitespace-nowrap">{STAGES[s.stage] ?? s.stage}</span>
                  {PER_CALL[s.stage] && <span className="block text-xs font-normal text-muted-foreground">{PER_CALL[s.stage]}</span>}
                </th>
                <td className="px-2 py-2 text-right">{num(s.requests)}</td>
                <td className="px-2 py-2">
                  {tokens ? (
                    <span className="flex items-center gap-2 whitespace-nowrap">
                      <span aria-hidden className="relative h-2 w-3/5 shrink-0 rounded-full bg-input/20">
                        <span className="absolute inset-y-0 left-0 min-w-1 rounded-full bg-foreground/60"
                              style={{ width: `${(100 * tokens) / maxTokens}%` }} />
                      </span>
                      <span>{num(tokens)}</span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">none (CPU)</span>
                  )}
                </td>
                <td className="px-2 py-2 text-right whitespace-nowrap">{(s.avg_latency_ms / 1000).toFixed(1)} s</td>
                <td className="px-4 py-2 text-right whitespace-nowrap">{isCpu(s) ? "–" : usd(s.cost_usd)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot className="border-t font-medium tabular-nums">
          <tr>
            <th scope="row" className="px-4 py-2 text-left">Total</th>
            <td className="px-2 py-2 text-right whitespace-nowrap">{num(totalCalls)} ({num(tfCalls)} Token Factory)</td>
            <td className="px-2 py-2">{num(totalTokens)}</td>
            <td />
            <td className="px-4 py-2 text-right">{usd(totalCost)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
    </>
  )
}
