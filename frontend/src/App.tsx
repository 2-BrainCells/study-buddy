import { useState } from "react"
import { api, type Learner, type PlanItem, type Video } from "@/api"
import { Player } from "@/Player"
import { Quiz } from "@/Quiz"
import { Setup } from "@/Setup"

// ponytail: a state machine instead of a router; three screens don't need URLs yet
type Screen =
  | { name: "setup" }
  | { name: "loading"; learner: Learner; video: Video }
  | { name: "play"; learner: Learner; video: Video; plan: PlanItem[] }
  | { name: "quiz"; learner: Learner; video: Video; plan: PlanItem[]; queued: PlanItem[] }

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

  return (
    <>
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4">
          <h1 className="text-sm font-semibold tracking-tight">Study Buddy</h1>
          {screen.name !== "setup" && (
            <button type="button" onClick={() => setScreen({ name: "setup" })}
                    className="rounded-md px-2 py-1 text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2">
              Switch learner
            </button>
          )}
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
