# Study Buddy: build plan

Read this at the start of every build session. CLAUDE.md holds the rules;
this file holds the plan, the data model and what "done" means each day.
Deadline: Sunday 18 Oct 2026, 3:30 PM IST. Aim to submit by 11:30 AM.

## The demo we are building towards

Two learners watch the same CS229 lecture 2 clip (10-15 min, around
gradient descent). Learner A has their own lecture 1-2 notes; learner B is
a beginner with no notes. The video pauses at different moments for each,
shows a short card for terms new to that learner, saves the term to their
profile, and ends with a 5-question quiz. Then the ed-tech dashboard shows
where learners struggled and an AMD usage panel shows what the AMD models
did and cost. Track 4 asks for: the experience changing for two audiences,
cost per experience, and who pays (ed-tech companies).

## Architecture

1. Per-video pipeline (runs once per video, cached, shared by all learners)
   - faster-whisper on CPU reads the video directly (PyAV, no ffmpeg step):
     transcript with word timestamps, cached in data/cache
   - split into sentence-aligned chunks (~600 words); one MiMo-V2.6-Flash call
     per chunk returns terms, a base explanation and 2 quiz questions per term
     (JSON mode + Pydantic); a reply that breaks the schema is retried once
     (stage terms_repair)
   - code finds each term in the word timestamps and pauses at the next
     . ? or ! (the LLM never returns timestamps); quiz options are shuffled
   - BGE-M3 on CPU embeds each term; store in pgvector
2. Per-learner loop
   - onboarding questionnaire (5 questions) seeds the learner profile
   - notes (typed Markdown/PDF now; handwriting photos as stretch) are
     indexed: terms extracted, embedded with BGE-M3, added to the profile
   - novelty check per video term: pgvector similarity + simple rules first
     (known / new / rare); only borderline terms go to the LLM, which also
     writes a one-line link to the learner's own notes
   - player (HTML5 video) loads the video cache + this learner's decisions
     once, then pauses locally at the sentence end for "new" terms
     (study mode) or shows a small card without pausing (glance mode);
     cap pauses per video and queue the rest for the end
   - "I already know this" button updates the profile
   - end-of-video quiz from cached questions; wrong answers logged
3. Ed-tech dashboard
   - per lecture: terms most learners found new or got wrong, pause counts
   - AMD usage panel: requests, input/output tokens, latency per pipeline
     stage; tokens per lecture hour and per learner; remaining daily quota
     and 429 count (X-RateLimit headers, GET /v1/usage). Every collector
     returns safe defaults on failure.

## Suggested data model (Postgres + pgvector)

- videos: id, title, source, licence, duration_s, processed_at
- segments: id, video_id, start_s, end_s, text
- terms: id, video_id, term, first_ts, pause_ts (sentence end),
  explanation, embedding vector(1024)
- quiz_questions: id, video_id, term_id, question, options (json), answer
- learners: id, name, questionnaire (json), level
- notes: id, learner_id, source (typed|photo), status (draft|reviewed), text
- learner_terms: learner_id, term_text, embedding, status
  (known|new|rare|wrong), source (questionnaire|notes|video|quiz), updated_at
- events: id, learner_id, video_id, type (pause|glance|known|quiz_answer),
  term_id, correct, ts, created_at
- stage_costs: id, video_id, learner_id (nullable), stage, model, requests,
  input_tokens, output_tokens, retries_429, latency_ms, created_at

## Token Factory client (one module, everything goes through it)

- base URL, key and model names from env (LLM_BASE_URL, RADEON_API_KEY,
  LLM_MODEL, VISION_MODEL); check GET /v1/models at startup
- every data call: response_format json_object + schema in the system prompt
  + Pydantic validation (no json_schema on Token Factory); reasoning_effort "none"
- retry only 429/502/503 with exponential backoff + jitter, honour
  Retry-After; max 8 concurrent, stay under ~20 requests/min
- log requests, tokens, retries and latency per stage to stage_costs
- `python -m pipeline check-endpoint` verifies key, models and one JSON call

## Progress (14 Oct)

- Wed foundation: done (commit 2926a19).
- Thu per-video pipeline: done a day early (commit fa45a87), on the 16.3-min
  lecture 2 clip: 26 terms, 52 quiz Qs, pause median 1.5 s / max 12.2 s.
- Measured: Whisper small.en 388 s CPU per 16.3 min (~24 s per lecture
  minute); LLM ~5.1k in / 6k out tokens per clip = ~$0.009 per lecture hour
  at MiMo list price; 60-120 s per chunk call; 1 of 10 chunk calls failed
  schema validation (repair retry added; not yet seen firing live).
- Open: term quality (near-duplicates like gradient / gradient descent, junk
  like "12th part"); parallel chunk calls before full 76-min lectures;
  Docker image not rebuilt since CPU-only torch.

## Build order and done criteria

### Wed 14 Oct: foundation
- docker-compose.yml with app (FastAPI), postgres (pgvector), web
- tables above created by a migration or init script
- Token Factory client + check-endpoint command
- Done when: `docker compose up -d` works, /health returns ok,
  check-endpoint passes, client tests pass with a fake model

### Thu 15 Oct: per-video pipeline
- ffmpeg + faster-whisper (CPU, word timestamps)
- chunking + batched term/explanation/quiz calls + BGE-M3 embeddings
- `python -m pipeline process <video>`; run via /process-video on lecture 2
- Done when: lecture 2 clip is cached with terms, pause timestamps,
  explanations and quiz questions, and stage_costs has a row per stage

### Fri 16 Oct: learner side
- questionnaire -> profile; typed notes indexing
- novelty check endpoint; player with study/glance modes and pause cap
- "I already know this"; end-of-video quiz
- Done when: learners A and B get different pauses on the same clip

### Sat 17 Oct: dashboard, stretch, demo
- ed-tech dashboard + AMD usage panel
- stretch: handwriting upload -> vision model/OCR -> review screen -> indexer
  (compare MinerU2.5-Pro, Qwen3.8-Flash-Next, MiniCPM-V-4.7-35B-A3B on 3 pages
  against the typed copy; keep the best). Drop if behind.
- friend test: 3-4 people, 10-min clip, 5-question quiz, with and without cards
- deploy to a CPU-only host; app works with cached data if Token Factory is down
- record the demo video

### Sun 18 Oct: submission (by 11:30 AM IST)
- slides incl. cost per lecture hour and per learner, Whisper accuracy vs the
  SEE transcript, friend-test result (labelled as a small pilot)
- README that runs from a fresh clone, CS229 credit, cover image
- submit on lablab with repo link, app URL, video and slides

## Out of scope this week

YouTube extension, embeddable player for ed-tech sites, syllabus-based tests,
live classes, Hinglish, Hindi handwriting. Mention them as next steps only.