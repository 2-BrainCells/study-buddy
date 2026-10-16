# Study Buddy

AI study buddy for lecture videos, built solo for the AMD Developer Hackathon
ACT III (Track 4), 12-18 Oct 2026. It pauses a lecture at sentence ends to
explain terms the learner doesn't know yet, based on their notes.
Buyer: ed-tech companies. Submission deadline: 18 Oct, 3:30 PM IST.

## Architecture
- Per-video pipeline (once per video): faster-whisper on CPU reads the video
  directly (word timestamps) -> LLM finds terms per chunk -> code places each
  pause at the end of the sentence that introduces the term -> near-duplicate
  terms dropped (BGE-M3 cosine >= 0.90, earliest wording wins) -> explanations
  and quiz questions -> Postgres cache.
- Per-learner loop: questionnaire + notes -> learner profile -> novelty check
  (profile match first, then one LLM call per learner per video judges which
  remaining terms the notes cover; it takes 100-210 s, so it runs in the
  background after notes are indexed) -> player pauses at the sentence end
  for the 5 new terms the transcript mentions most; the rest are saved for
  the end.
- Handwritten notes: photo -> vision model or OCR -> Markdown -> learner
  review -> indexer.
- Ed-tech dashboard: where learners struggle (pauses, wrong quiz answers),
  plus an AMD usage panel: requests, tokens and latency per pipeline stage,
  tokens per lecture hour and per learner (from stage_costs), and the daily
  budget from GET /v1/usage (checked 16 Oct: $1/day cost cap, 20 requests/min,
  Token Factory's own billed cost; there are no X-RateLimit headers on
  /models). 429s come from stage_costs.retries_429. Every usage collector
  returns safe defaults on failure, so the panel never crashes.

## Stack
- backend/: Python 3.11, FastAPI, Postgres + pgvector, BGE-M3 and
  faster-whisper on CPU. Local development uses the conda env "study-buddy";
  install packages there and don't create other environments. The app
  container has its own Python and installs from backend/requirements.txt.
- frontend/: React, Vite, TypeScript, Tailwind, shadcn/ui (Radix). No chart
  library: the timelines and bars are plain CSS (Recharts was tried and removed).
  This project uses Vite, not my default Next.js: it's a static app served
  behind FastAPI. All API routes are under /api; in dev, Vite proxies /api
  to localhost:8001. Design rules live in design/BRIEF.md (hybrid theme:
  light paper page, dark lecture band; amber pause, grey saved, teal
  skipped). Colours and fonts come only from the tokens in
  frontend/src/index.css. index.html sets darkreader-lock on purpose.
- docker-compose.yml: app, postgres. No web container: FastAPI will serve
  frontend/dist (decided 15 Oct). The app mounts data/videos read-only as
  VIDEO_DIR. No GPU container. Postgres is on host port 5433, because a Windows Postgres 17
  service holds 5432. Local DATABASE_URL uses localhost:5433; the app
  container uses postgres:5432.

## Models: AMD Token Factory (the hackathon's AMD requirement)
- All LLM and vision calls go to the Token Factory OpenAI-compatible API.
  Read RADEON_API_KEY, LLM_BASE_URL, LLM_MODEL and VISION_MODEL from env
  vars; never hard-code them. Check GET /v1/models at startup, because
  model names change.
- LLM_MODEL is MiMo-V2.6-Flash. Optional NOVELTY_MODEL gives the novelty check
  its own model: Gemma-4-31B-IT since 16 Oct (same accuracy on our 20 labels,
  10-20x faster, about 4x cheaper; see DECISIONS.md #66). If that model fails
  or disappears (Gemma vanished from Token Factory for part of 16 Oct), the
  check falls back to LLM_MODEL, then to the offline path. Token Factory supports JSON mode
  (response_format json_object) but not json_schema (structured_outputs:
  false, checked 14 Oct). Put the schema in the system prompt and validate
  every reply with Pydantic.
- Always send reasoning_effort "none" or "low"; thinking otherwise uses up
  max_tokens and replies come back empty. GLM-5.3-Flash rejects "none"; use
  "low" there.
- Limits: about 20 requests/min, 8 concurrent, a daily spend cap. Batch
  work (one call per transcript chunk, not per term), retry only 429/502/503
  with exponential backoff and jitter, and cache every result.
- Log requests and token usage per pipeline stage to the stage_costs table.
- Token Factory has no embeddings or audio endpoints; those run on CPU.
- Send only lecture content and study notes; prompts are logged ~2 days.

## Rules
- Never read or edit .env. Never commit anything in data/.
- Never use the Token Factory key for Claude Code itself.
- Lecture videos are CS229 (Andrew Ng, Stanford Engineering Everywhere,
  CC BY-NC-SA 4.0); keep the credit in README.md.
- Tests never call real models; use fakes.
- Write all code fresh during the hackathon (from 12 Oct). Earlier projects,
  such as my Agentic-KYC repo, are reference for ideas only; never copy
  their code.
- The build plan, data model and daily done criteria are in docs/PLAN.md.
Read it at the start of each build session.
- Errors hit and decisions made (cause and resolution for each) are logged
  in docs/DECISIONS.md. Add a row whenever something breaks or a choice is
  made.

## Commands
- Run everything: docker compose up -d
- Backend tests: python -m pytest -q (from backend/)
- Lint: python -m ruff check backend
- Frontend dev server: npm run dev (from frontend/)
- Frontend tests: npm test (from frontend/)
- Novelty eval (from backend/): python -m pipeline eval-novelty --learner <id> --video <id> --labels ../data/notes/labels_a.csv
- Check the model endpoint: python -m pipeline check-endpoint (add --model <name> to probe one model)
- Check what quota Token Factory reports (no tokens used): python -m pipeline check-usage
- Reset sessions before a recording (dry run without --yes): python -m pipeline reset-demo --yes
- Public deploy: set DEMO_MODE=1 (no new learners or notes, so strangers can't spend the
  $1/day model budget). Without a model, plans still load from cached data.
- Process a video (from backend/): python -m pipeline process <video-path> --title "<title>"