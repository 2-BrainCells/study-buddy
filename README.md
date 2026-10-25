# Study Buddy

[![CI](https://github.com/2-BrainCells/study-buddy/actions/workflows/ci.yml/badge.svg)](https://github.com/2-BrainCells/study-buddy/actions/workflows/ci.yml)

An AI study buddy for lecture videos. It pauses the lecture at the end of a sentence to explain a term **this learner** doesn't know yet, based on their own notes, then quizzes them at the end.

**Live demo:** https://study-buddy-vb9b.onrender.com/
(Public demo mode: pick learner A or B. The first load after 15 idle minutes takes about a minute while the free host wakes up.)

Built solo for the **AMD Developer Hackathon ACT III, Track 4** (12–18 Oct 2026). Buyer: ed-tech companies that host lecture video.

## What it does

Two learners watch the same 16-minute CS229 clip on gradient descent:

- **Learner A** has their own lecture notes. Study Buddy skips the terms A already knows, from their notes ("learning rate") or the onboarding questionnaire ("linear regression"), and pauses only on new ones.
- **Learner B** is a beginner with no notes. The video pauses on the 5 new terms the lecturer mentions most, and saves the rest for the end.

At each pause, a short card explains the term. "I already know this" adds the term to the learner's profile. The video ends with a quiz on the new terms. An ed-tech dashboard shows where learners struggled (pauses, wrong answers), and an **AMD usage panel** shows what the models did and what they cost.

## How it works

```
Per video (once, cached, shared by every learner)
  video ─▶ faster-whisper (CPU, word timestamps)
        ─▶ LLM per ~600-word chunk: terms + explanations + 2 quiz Qs each
        ─▶ code places each pause at the end of the sentence that introduces the term
        ─▶ BGE-M3 (CPU) drops near-duplicate terms (cosine ≥ 0.90)
        ─▶ Postgres + pgvector

Per learner
  questionnaire + notes ─▶ profile ─▶ novelty check (profile match, then one LLM call
  per learner per video: which terms do the notes cover?) ─▶ player pauses on the new ones

Dashboard
  events (pauses, "I know this", quiz answers) + stage_costs + Token Factory budget
```

## AMD Token Factory

All LLM calls go to AMD Token Factory's OpenAI-compatible API:

| Stage | Model | Why |
|---|---|---|
| Terms, explanations, quiz questions, reading notes | MiMo-V2.6-Flash | The default model (`LLM_MODEL`) |
| Novelty check (do the notes cover this term?) | Gemma-4-31B-IT | Same accuracy as MiMo on our labels, 10–20× faster, about 4× cheaper ([DECISIONS #66](docs/DECISIONS.md)) |

- **Fallbacks:** if Gemma is unavailable, the novelty check falls back to MiMo, then to an offline path. The app always loads from cached data.
- **Valid output:** Token Factory supports JSON mode but not `json_schema`. So the schema goes in the prompt, every reply is validated with Pydantic, and a reply that breaks the schema is retried once.
- **Rate limits:** only 429, 502 and 503 are retried, with exponential backoff and jitter. Work is batched (one call per transcript chunk, not per term), and every result is cached.
- **Cost logging:** requests, tokens, retries and latency are logged per pipeline stage. The usage panel turns them into cost per lecture hour and per learner, next to the live daily budget from `GET /v1/usage`.
- **CPU only:** embeddings (BGE-M3) and speech-to-text (faster-whisper) run on CPU, because Token Factory has no embeddings or audio endpoints.

## Numbers

Measured on the demo clip. Small samples are marked as such; details are in [docs/DECISIONS.md](docs/DECISIONS.md).

| What | Value |
|---|---|
| LLM cost per lecture hour (list price) | about **$0.008** |
| Novelty check per learner per video (Gemma) | about $0.00009, 9 s (average of 4 calls) |
| Whisper small.en on CPU | about 24 s per lecture minute |
| Pause delay after a term's first mention | median 1.5 s |
| Novelty check vs hand labels ("known") | precision 0.50, recall 0.64; **n = 21 terms, one learner**. Most disagreements are about what the label means, not model errors ([#74](docs/DECISIONS.md)) |

## Run it locally

You need Docker Desktop, Python 3.11 (we use a conda env), Node 22, and an AMD Token Factory API key.

```bash
git clone https://github.com/2-BrainCells/study-buddy.git
cd study-buddy
cp .env.example .env          # fill in RADEON_API_KEY, LLM_BASE_URL, LLM_MODEL, VISION_MODEL, NOVELTY_MODEL
docker compose up -d postgres # Postgres + pgvector on host port 5433; the schema is created on first start
```

Process a lecture. The pipeline runs on your machine, not in the container:

```bash
# Linux only, first: pip install torch --index-url https://download.pytorch.org/whl/cpu (the default wheel bundles CUDA)
pip install -r backend/requirements.txt
# Download lecture 2 (MP4) from https://see.stanford.edu/Course/CS229 into data/videos/.
# The demo uses a 16-minute excerpt starting at about 25:00; any excerpt works.
cd backend
python -m pipeline check-endpoint   # key, models and one JSON call
python -m pipeline process ../data/videos/<your-clip>.mp4 --title "CS229 Lecture 2: Gradient descent (clip)"
```

Then run the app:

```bash
docker compose up -d --build   # API + built frontend on http://localhost:8000
```

To work on the code instead: run `uvicorn app.main:app --port 8001` from `backend/` (with `DATABASE_URL` pointing at `localhost:5433`), and `npm run dev` from `frontend/`. Vite proxies `/api` to port 8001.

A full 76-minute lecture is untested: the chunk calls run one after another, so it would take a while.

## Deploy

The live demo runs one Docker image on Render (free tier, Singapore), with Neon Postgres. The image holds the built frontend and the demo clip, and no torch. `DEMO_MODE=1` blocks new learners and notes, so visitors can't spend the model budget; it runs in about 60 MB of RAM. How we chose the host and set it up is in [DECISIONS #71–76](docs/DECISIONS.md).

## Access

- **Demo learners** (A and B) are open to everyone: no sign-up, no login.
- **Real learners** sign up with an invite code (`INVITE_CODE`; with it set, sign-up works even in demo mode). The server returns a random token once and stores only its SHA-256 hash. The browser keeps the token and sends it as `Authorization: Bearer …`; without the right token, a real learner's plan, clicks, notes and events return 401.
- **Nobody sees real learners' names:** `/api/learners` lists demo learners only, and the public usage panel shows real learners as "Learner 7". The dashboard has only aggregates.
- Why it's built this way: [DECISIONS #81–83](docs/DECISIONS.md).

## Tests

```bash
cd backend && python -m pytest -q   # 65 tests; models are always faked
# the 18 database tests need a separate Postgres database (they empty it); without one they're skipped:
# TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/study_buddy_test, after running backend/db/init.sql on it
cd frontend && npm test             # 10 tests
python -m ruff check backend
```

## Repo layout

```
backend/app/        FastAPI: learner profile, plan, events, dashboard, usage
backend/pipeline/   transcription, term extraction, embeddings, Token Factory client, CLI
backend/db/         schema (init.sql)
frontend/src/       React + Vite + Tailwind: setup, player, quiz, dashboard
design/BRIEF.md     design rules
docs/PLAN.md        build plan and daily progress
docs/DECISIONS.md   every error and decision, with cause and resolution
```

## Limitations

- One demo clip, and the novelty check is measured on one learner's notes (n = 21). The labelling question ("covered by my notes" vs "I'd want a card") is still open.
- Handwritten notes (photo → vision model → Markdown) are designed but not built.
- The free host sleeps when idle, so the first visit takes about a minute.

## Credits and licence

**Lecture video:** CS229 Machine Learning, Andrew Ng, [Stanford Engineering Everywhere](https://see.stanford.edu/Course/CS229), licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The demo clip and everything derived from it (transcript, terms, explanations, quiz questions) stay under CC BY-NC-SA 4.0 and are used non-commercially. A customer would run Study Buddy on their own lectures.

**Code:** [MIT](LICENSE).
