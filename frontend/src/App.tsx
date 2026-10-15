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
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-8 flex items-baseline justify-between gap-4">
        <h1 className="text-xl font-semibold">Study Buddy</h1>
        {screen.name !== "setup" && <p className="text-sm text-muted-foreground">{screen.learner.name}</p>}
      </header>
      {screen.name === "setup" && <Setup onStart={start} error={error} />}
      {screen.name === "loading" && (
        <p role="status">Preparing {screen.learner.name}'s plan… the first time can take a few minutes.</p>
      )}
      {screen.name === "play" && (
        <Player learner={screen.learner} video={screen.video} plan={screen.plan}
                onDone={(queued) => setScreen({ ...screen, name: "quiz", queued })} />
      )}
      {screen.name === "quiz" && (
        <Quiz learner={screen.learner} video={screen.video} plan={screen.plan} queued={screen.queued}
              onBack={() => setScreen({ name: "setup" })} />
      )}
    </main>
  )
}
