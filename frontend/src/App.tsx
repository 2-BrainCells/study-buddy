import { useState } from "react"
import { api, type Learner, type PlanItem, type Video } from "@/api"
import { Dashboard } from "@/Dashboard"
import { Player } from "@/Player"
import { Quiz } from "@/Quiz"
import { Setup } from "@/Setup"

// ponytail: a state machine instead of a router; four screens don't need URLs yet
type Screen =
  | { name: "setup" }
  | { name: "loading"; learner: Learner; video: Video }
  | { name: "play"; learner: Learner; video: Video; plan: PlanItem[] }
  | { name: "quiz"; learner: Learner; video: Video; plan: PlanItem[]; queued: PlanItem[] }
  | { name: "dashboard"; video: Video }

export default function App() {
  const [screen, setScreen] = useState<Screen>({ name: "setup" })
  const [error, setError] = useState("")

  function start(learner: Learner, video: Video) {
    setError("")
    setScreen({ name: "loading", learner, video })
    api
      .plan(learner.id, video.id)
      .then((plan) => setScreen({ name: "play", learner, video, plan }))
      .catch((e) => {
        setError(String(e))
        setScreen({ name: "setup" })
      })
  }

  function openDashboard() {
    setError("")
    api
      .videos()
      .then((v) => (v[0] ? setScreen({ name: "dashboard", video: v[0] }) : setError("No processed video yet.")))
      .catch((e) => setError(String(e)))
  }

  const navClass = (active: boolean) =>
    `rounded-md px-2 py-1 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 ${
      active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4">
          <h1 className="text-sm font-semibold tracking-tight">Study Buddy</h1>
          <nav aria-label="Main" className="flex items-center gap-2">
            <button type="button" onClick={() => setScreen({ name: "setup" })}
                    aria-current={screen.name === "setup" ? "page" : undefined}
                    className={navClass(screen.name === "setup")}>
              {screen.name === "setup" || screen.name === "dashboard" ? "Learners" : "Switch learner"}
            </button>
            <button type="button" onClick={openDashboard} aria-current={screen.name === "dashboard" ? "page" : undefined}
                    className={navClass(screen.name === "dashboard")}>
              Dashboard
            </button>
          </nav>
        </div>
      </header>
      {screen.name === "play" ? (
        // full width: the player draws its own dark lecture band edge to edge
        <main>
          <Player learner={screen.learner} video={screen.video} plan={screen.plan}
                  onDone={(queued) => setScreen({ ...screen, name: "quiz", queued })} />
        </main>
      ) : (
        <main className="mx-auto max-w-6xl px-4 py-8">
          {screen.name === "setup" && <Setup onStart={start} error={error} />}
          {screen.name === "dashboard" && <Dashboard video={screen.video} />}
          {screen.name === "loading" && (
            <p role="status" className="text-muted-foreground">
              Preparing {screen.learner.name}'s plan… the first time can take a few minutes.
            </p>
          )}
          {screen.name === "quiz" && (
            <Quiz learner={screen.learner} video={screen.video} plan={screen.plan} queued={screen.queued}
                  onBack={() => setScreen({ name: "setup" })} />
          )}
        </main>
      )}
    </>
  )
}
