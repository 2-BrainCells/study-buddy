# Study Buddy

AI study buddy for lecture videos, built solo for the AMD Developer Hackathon
ACT III (Track 4), 12-18 Oct 2026. It pauses a lecture at sentence ends to
explain terms the learner doesn't know yet, based on their notes.
Buyer: ed-tech companies. Submission deadline: 18 Oct, 3:30 PM IST.

## Architecture
- Per-video pipeline (once per video): faster-whisper on CPU reads the video
  directly (word timestamps) -> LLM finds terms per chunk -> code places each
  pause at the end of the sentence that introduces the term -> explanations
  and quiz questions -> Postgres cache.
- Per-learner loop: questionnaire + notes -> learner profile -> novelty check
  (profile match first, then one LLM call per learner per video judges which
  remaining terms the notes cover; BGE-M3 finds the nearest known term for
  the card) -> player pauses at the sentence end.
- Handwritten notes: photo -> vision model or OCR -> Markdown -> learner
  review -> indexer.
- Ed-tech dashboard: where learners struggle (pauses, wrong quiz answers),
  plus an AMD usage panel: requests, tokens and latency per pipeline stage,
  tokens per lecture hour and per learner, and remaining daily quota and
  429s from the X-RateLimit headers and GET /v1/usage. Every usage collector
  returns safe defaults on failure, so the panel never crashes.

## Stack
- backend/: Python 3.11, FastAPI, Postgres + pgvector, BGE-M3 and
  faster-whisper on CPU. Local development uses the conda env "study-buddy";
  install packages there and don't create other environments. The app
  container has its own Python and installs from backend/requirements.txt.
- frontend/: React, Vite, TypeScript, Tailwind, shadcn/ui, Recharts. This
  project uses Vite, not my default Next.js: it's a static app served
  behind FastAPI.
- docker-compose.yml: app, postgres (web container decided Friday). No GPU
  container. Postgres is on host port 5433, because a Windows Postgres 17
  service holds 5432. Local DATABASE_URL uses localhost:5433; the app
  container uses postgres:5432.

## Models: AMD Token Factory (the hackathon's AMD requirement)
- All LLM and vision calls go to the Token Factory OpenAI-compatible API.
  Read RADEON_API_KEY, LLM_BASE_URL, LLM_MODEL and VISION_MODEL from env
  vars; never hard-code them. Check GET /v1/models at startup, because
  model names change.
- LLM_MODEL is MiMo-V2.6-Flash. Token Factory supports JSON mode
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

## Commands
- Run everything: docker compose up -d
- Backend tests: python -m pytest -q (from backend/)
- Lint: python -m ruff check backend
- Frontend dev server: npm run dev (from frontend/)
- Check the model endpoint: python -m pipeline check-endpoint
- Process a video (from backend/): python -m pipeline process <video-path> --title "<title>"