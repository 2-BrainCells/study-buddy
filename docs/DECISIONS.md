# Errors and decisions log (12–16 Oct 2026)

This log lists every error we hit and every design decision we made while building Study Buddy. Each entry
gives its cause, how it was resolved, and the commit that holds the fix. Numbers come from runs in this
repo; small samples are marked as such.

## Handoff summary (Fri 16 Oct, 9 AM IST; everything up to `d71b0cf` is pushed)

**Built and working:**
- **Per-video pipeline (CPU plus Token Factory):** Whisper transcription, term extraction, pauses at sentence ends, the near-duplicate filter, explanations and quiz questions, all cached in Postgres. The 16-minute lecture 2 clip is video 3: 20 terms, 40 quiz questions.
- **Learner side:**
  - the questionnaire and typed notes build a profile
  - the novelty check runs on Gemma, falling back to MiMo, then to offline
  - the plan API, plus `eval-novelty` against your labels
- **Player:**
  - study and glance modes, with 5 pauses per video, ranked by how often the transcript mentions each term
  - "I already know this", captions, the session and skipped lists, and the quiz
  - events are logged
- **Dashboard:** "where learners struggle", plus the AMD usage panel (cost per lecture hour and per learner, and the budget from `GET /v1/usage`).
- **Safety:** demo mode (`DEMO_MODE=1`), the offline fallback, and `reset-demo`.
- **Tests:** 41 backend and 8 frontend. The design critic passed the player and the dashboard.

**Known bugs and rough edges:**
- Junk terms still pause: "colon equals" for learner A (#23).
- Novelty accuracy is modest: precision about 0.5, recall 0.6, from n = 20, one learner (#28, #66).
- The dashboard has almost no real data yet (2 events).
- The Docker image hasn't been rebuilt since the CPU-only torch change, and FastAPI doesn't serve `frontend/dist` yet.
- The repair retry (#4) has never fired live.
- Unused Vite demo files are still in `frontend/`.
- Your local API on port 8001 needs restarting.
- Your `.env.example` edit isn't committed yet.

**Key decisions and why** (details in the rows below):
- **Models:** MiMo-V2.6-Flash for extraction, notes and quizzes; Gemma-4-31B-IT for the novelty check, because it matched MiMo's accuracy and was 10–20× faster and about 4× cheaper (#66).
- **Output format:** JSON mode with Pydantic validation, because Token Factory has no `json_schema` (#1).
- **Thresholds:**
  - duplicate terms at BGE-M3 ≥ 0.90 (#21)
  - similarity bands dropped, because they were near chance (#27)
  - 5 pauses per video, ranked by mentions (#35)
- **Batching:** one LLM call per ~600-word chunk, and one novelty call per learner per video, run in the background (#19, #30).
- **Schema:**
  - `videos.file` added
  - `learner_terms.source` records where a known term came from: questionnaire, notes, or a click
  - API routes moved under `/api`
- **Frontend:** Vite rather than Next.js, no web container, no chart library (#40, #60).

**Left from PLAN.md** (sizes and order in the plan file `what-s-left-in-the-cozy-sunrise.md`):
- **Must do:** the Docker image and deploy (pick a host), recording the demo, the README with the CS229 credit, the slides, and submitting by 11:30 AM Sunday.
- **Should do:** the friend test (a small pilot), Whisper WER against the SEE transcript, deciding on junk terms, and asking in the Discord whether Gemma via Token Factory counts for the prize.
- **Could do:** handwritten notes, and full-length lectures.

**Type:**
- **Error:** something broke or gave wrong results.
- **Hindrance:** a tool or the environment got in the way.
- **Decision:** a choice between options, with the reason.

**Open** means not resolved yet.

## 1. Model API (AMD Token Factory)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 1 | Hindrance | `json_schema` structured output was rejected | Token Factory models report `structured_outputs: false` (checked 14 Oct) | Use `json_object` mode, put the schema in the system prompt, and validate every reply with Pydantic | 2926a19 |
| 2 | Error | GLM-5.3-Flash returned 422 for `reasoning_effort="none"` | That model accepts only low, medium or high | Send "none" to MiMo and "low" to GLM; documented in CLAUDE.md | 2926a19 |
| 3 | Error | Replies could come back empty | Thinking tokens use up `max_tokens` | Always send none or low reasoning; `EmptyReplyError` is counted and reported, not hidden | 2926a19 |
| 4 | Error | 1 of 5 transcript chunks failed validation (MiMo nested a list inside `options`) | JSON mode guarantees valid JSON, not the right shape | One repair retry with the validation error in the prompt (stage `terms_repair`); chunks that still fail are counted | fa45a87 (the repair hasn't fired live yet) |
| 5 | Decision | `max_tokens=4000` for term extraction | 8 terms × 2 quiz questions needs more than 2,000 tokens | Set in `process.py` | fa45a87 |
| 6 | Decision | Retry only on 429/502/503, with exponential backoff, jitter and Retry-After; at most 8 concurrent requests, with a 3 s gap | About 20 requests per minute plus a daily spend cap | Built into the one client; every call logged per stage to `stage_costs` | 2926a19 |

## 2. Environment and tooling (Windows, Docker, shells)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 7 | Error | Postgres connections to port 5432 reached the wrong server | A Windows Postgres 17 service already held 5432 | Docker Postgres moved to host port 5433; local `DATABASE_URL` uses 5433, and the app container uses `postgres:5432` | fa45a87, 9fb3083 |
| 8 | Error | `DATABASE_URL` failed to parse | `.env` contained `DATABASE_URL=DATABASE_URL=...` | `.env` fixed by hand; `.env.example` corrected | 9fb3083 |
| 9 | Hindrance | The assistant couldn't read `.env` or `.env.example`, and a script that loaded `.env` was blocked | Project safety rules protect secrets | `.env` is edited by hand; the app loads it through `uvicorn --env-file` / `load_dotenv` | By design |
| 10 | Decision | No separate ffmpeg step | faster-whisper reads the video directly through PyAV | Dropped from the plan and the docs | 46556b6 |
| 11 | Hindrance | The Hugging Face model cache is about 4.35 GB | Windows has no symlinks, so cached files are duplicated | Accepted | Noted |
| 12 | Hindrance | Several PowerShell 5.1 quirks broke commands | Here-strings don't pipe into `git commit -F -`. `conda run` passes no stdin. `curl` is an alias. `Get-Content -Raw` attaches file properties, which `ConvertTo-Json` serialised, so the notes POST got a 422 | Bash heredocs for commits, scripts in a scratch folder, `curl.exe` or `Invoke-RestMethod`, and `[IO.File]::ReadAllText` | Workarounds |
| 13 | Error | `eval-novelty` crashed with `UnicodeDecodeError` | PowerShell 5.1's `>` writes UTF-16, and the label export command used it | The eval reads both UTF-16 and UTF-8 | d68c44b |
| 14 | Error | `transcribe.py` got a syntax error after an automated edit | A Python heredoc turned `\n` escapes into real newlines | Rewritten with a direct file edit | 823172e |
| 15 | Hindrance | `rm -rf` was blocked | A project hook blocks recursive deletes | The unused Vite demo files stay untracked and can be deleted by hand | **Open** (cosmetic) |
| 16 | Hindrance | Port 8001 was already in use | A developer uvicorn with `--reload` was running there | Assistant checks ran on 8002; Vite proxies to 8001 | Workaround |
| 17 | Hindrance | Waiting loops (`sleep`) were blocked while waiting for Stitch | A tool rule against waiting loops | Gave up on the Stitch mockups (see #46) | Workaround |

## 3. Per-video pipeline and term quality

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 18 | Decision | The LLM never returns timestamps; code pauses at the next `.`, `?` or `!` after the term | LLM timestamps would be unreliable, while Whisper's word timestamps are exact | `place()` in `terms.py`; on the clip, the median delay after the first mention is 1.5 s and the maximum 12.2 s | fa45a87 |
| 19 | Decision | One LLM call per sentence-aligned chunk of about 600 words | Rate limits, and whole sentences give the model context | `chunk()` | fa45a87 |
| 20 | Error | Nested duplicates, e.g. "gradient" and "gradient descent" at the same pause | The LLM lists a term and part of it | A prompt rule, plus `drop_nested` (same pause, contained in a longer term) | d68c44b |
| 21 | Error | Near-duplicates at different pauses: local optimum / local optima, initial point / initial starting point | Same idea, different wording | `drop_near_duplicates` at BGE-M3 cosine ≥ 0.90. On the clip, the duplicate pairs scored 0.90–0.91 and the distinct pairs (learning rate / rule, local / global minimum) scored 0.78–0.81. The threshold is tuned on one clip | 156a47c |
| 22 | Decision | Remove the clip's two duplicates in place instead of re-running the pipeline | A re-run changes the whole term set and the video id, deletes events, invalidates labels and cached verdicts, and costs LLM time | Deleted in place (20 terms, 40 quiz questions); the filter now runs on every future pipeline run | 156a47c |
| 23 | Error | Junk terms such as "12th part", "questions", "colon equals" | The LLM picks everyday words | A prompt rule removed some; "colon equals" still paused for learner A until 16 Oct, when a second rule (no notation or symbols read aloud) and a re-run gave video 4 with no junk (see #70) | Resolved 16 Oct (one run, so the rule's effect isn't proven) |
| 24 | Decision | Shuffle quiz answer options before saving | The LLM tends to put the right answer in the same place | `shuffle_options` with a seeded RNG, so results are reproducible | fa45a87 |

## 4. Learner profile and novelty check

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 25 | Decision | Learner A's notes are typed Markdown; handwriting is a Saturday stretch goal | Time, and the risk of a vision model or OCR step | Notes in `data/notes/learner_a.md` (not committed) | Decided 14 Oct |
| 26 | Error | Bugs in the first learner-side code: `.enncode`, a stray `)` in `to_vector`, `"know"`, `"boderline"`, `extras=` | Typos in code that hadn't been run yet | All fixed, with tests for `to_vector`, `classify` and `chunk_text` | d68c44b |
| 27 | Error | Similarity bands couldn't tell known terms from new ones: precision 0.80, recall 0.36, AUC about 0.61 (22 labelled terms) | BGE-M3 scores every short term between 0.52 and 0.73, so no threshold separates known from new | Bands dropped | d68c44b |
| 28 | Error | Notes indexing missed ideas written as maths (the learning rate appears only as α) | The extraction prompt says to copy terms as written | One LLM coverage call per learner per video reads the notes directly. Precision 0.50–0.55 and recall 0.55 over 3 runs; 0.50 / 0.60 on 20 terms. It trades missed pauses for extra ones | d68c44b; trade-off **open** |
| 29 | Hindrance | Inconsistent labels, e.g. local optimum = 1 but local optima = 0 | The label question was ambiguous ("studied the idea" vs "would want a card") | Labels fixed before the new results were seen; the prompt is frozen to avoid tuning it on the test set | Label question **open** |
| 30 | Error | The coverage call takes 100–210 s | MiMo latency | Runs as a background task after notes are saved, so the plan is cached before the player asks for it | 823172e |
| 31 | Error | Skip reasons read "in profile", which doesn't say why a term is known | The profile stored only a status | Reasons now come from the source (questionnaire, notes, or marked known). Covered verdicts are stored with source `notes`, and 8 existing rows were migrated | 988c306, 6ce7569 |
| 32 | Decision | Re-indexing notes keeps "I already know this" clicks | A delete-all would erase those clicks | Only cached `new` verdicts are deleted | 823172e |

## 5. Player behaviour

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 33 | Decision | Check for pauses every frame (`requestAnimationFrame`), not only on `timeupdate` | `timeupdate` fires only about every 250 ms, so pauses would cut into the next word | A frame loop, measured at 61 checks per second in a visible window | 823172e |
| 34 | Error | Pauses were silently skipped when the window was hidden | Chrome throttles a hidden window to about 2 frames per second or stops it; the old guard (a jump of more than 1 s = a seek) mistook that for a seek | Seeks are detected from `video.seeking` and the `seeking` event; `timeupdate` backs up the frame loop; a test covers long gaps | 823172e |
| 35 | Error | All 5 of learner B's pauses fell in the first 3 minutes of a 16-minute clip | The cap took the first 5 stops in time order | Pause at the 5 stops whose terms the transcript mentions most, kept in video order. Even spacing was rejected because it pushed "gradient descent" (24 mentions) to the end | 156a47c |
| 36 | Decision | Serve the video through FastAPI's `FileResponse` | The browser needs Range support to seek | A Range request returns 206 | 823172e |
| 37 | Decision | WebVTT captions built from the Whisper segments | Accessibility, and the data already existed | `to_vtt`, with a test | 823172e |
| 38 | Decision | Event logging never blocks playback | A failed log shouldn't stop the lecture | Failures go to `console.error`: visible, not swallowed | 823172e |
| 39 | Hindrance | Browser checks wrote test events | Playing into a pause logs real events | Each round's test rows were deleted by id; real events were kept | Done each round |

## 6. Frontend setup and architecture

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 40 | Decision | Vite instead of Next.js; no web container | It's a static app served behind FastAPI | Vite proxies `/api` in development; FastAPI will serve `frontend/dist` | 823172e |
| 41 | Decision | All API routes under `/api` | Avoids collisions with static files | `APIRouter(prefix="/api")`; `/health` stays at the root | 823172e |
| 42 | Hindrance | `shadcn init` stopped at interactive prompts, and the preset `radix-nova` was rejected | The newer CLI asks for a component library and a preset | Run with `-b radix -p nova` | 823172e |
| 43 | Hindrance | `baseUrl` is deprecated in TypeScript 6 | A TypeScript 6 change | The path alias is set through `paths` only | 823172e |
| 44 | Decision | Native checkboxes and toggles; shadcn only for button, card, input, label and textarea | Newer shadcn component APIs differ between versions | Fewer APIs that could change | 823172e |
| 45 | Decision | Vitest for the frontend logic tests | It's native to Vite; `node --test` can't resolve the `@/` alias | 8 tests on the pause and quiz logic | 823172e |

## 7. Design

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 46 | Hindrance | Stitch mockups timed out | Generation was slow, and waiting loops were blocked | Three directions described in text, with contrast computed for each palette | — |
| 47 | Decision | Direction B: dark, amber pause timeline, "Why it paused" line | Chosen for the buyer audience | The design critic failed it 3 times (phone video not staying stuck, sideways overflow, card below the fold) before passing it at 8/7/8/8 | 988c306 |
| 48 | Error | Feedback: the design was too dark and too minimal | The Dark Reader browser extension was repainting the pages dark, and the brief carried a "no dashboard clutter" rule that nobody had asked for | Hybrid theme (light page, dark lecture band), a profile strip, session and skipped lists, a `darkreader-lock` meta tag, and a corrected brief. The critic passed it at 8/8/8/8 | 6ce7569 |
| 49 | Error | Faint marks and broken layouts flagged by the critic | Amber on paper was about 1.8:1, form edges 1.39:1, and a no-wrap line stretched the phone layout to 521 px | Dark amber `--pause-ink` (5.4:1), form edges at 3.2–3.3:1, and `grid-cols-1` | 988c306, 6ce7569 |

## 8. Process

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 50 | Hindrance | The Chrome extension disconnected or lost its tab group | Long scripts (over 10 s) and a hidden window | Reconnected with `/chrome`; shorter scripts and fresh tabs | Workaround |
| 51 | Decision | Walkthroughs for new build steps unless asked to "do it" | The developer's learning goal | Followed; "do it" / "fix it" switched to building | Ongoing |
| 52 | Decision | Never commit `data/` or `.env`; commits only through `/checkpoint`; every push confirmed | Project rules | Files staged explicitly, with a check before every commit | Ongoing |

## 9. Dashboard and AMD usage panel (16 Oct)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 53 | Hindrance | The planned quota sources were unverified (`X-RateLimit` headers, `GET /v1/usage`) | They had been written into the plan before anyone checked | `python -m pipeline check-usage` probed them: no `x-ratelimit` headers on `/models`, but `GET /usage` reports a $1/day cost cap, 20 requests/min and Token Factory's own billed cost. Docs corrected | This commit |
| 54 | Decision | Costs shown at list price, next to Token Factory's own billed figure | The bill is lower because prompt-cache hits are cheaper (a 37% hit rate in the last 24 h) | The panel states both, and labels which is which | This commit |
| 55 | Decision | The quota collector keeps only the panel's fields | `GET /usage` also returns organisation and project ids and a list of recent requests | `quota_summary()` whitelists fields; a test checks that ids are dropped | This commit |
| 56 | Decision | The dashboard shows real events only; no seeded or fake data | Fabricated data would mislead the buyer | An empty state until real sessions (friend test, demo run-throughs) exist | This commit |
| 57 | Decision | "Struggle" score = learners who paused + wrong quiz answers | Needed a simple ranking; nothing validated exists | Labelled on screen as pauses + wrong quiz answers; documented as a heuristic | This commit |
| 58 | Error | The token chart and budget bar used teal, the colour that means "already known" | Status colours were reused for an unrelated measure | Neutral ink for magnitudes, amber only where it means pauses | This commit |
| 59 | Error | The first dashboard failed the design critic (originality 5, craft 6, functionality 5) | The AMD numbers were below the fold (y=1176), a single-bar chart on a 0–4 axis, a 20-row table of zeros, "25 requests" included CPU runs, and raw stage ids | An "at a glance" row with both halves above the fold, a lecture strip in the player's timeline style, only terms with activity shown, only Token Factory requests counted, readable stage names | This commit |
| 60 | Decision | Recharts removed again | Both charts were replaced by a CSS strip and inline bars, which read better with this little data | `npm uninstall recharts`; one dependency fewer | This commit |
| 61 | Error | The phone dashboard overflowed by 14 px although my check said it didn't | I compared `scrollWidth` with `innerWidth`, which includes the 15 px scrollbar; the real cause was a grid with no column template below `lg` (the same mistake as #49) | `grid-cols-1` on the grid; checks now compare `scrollWidth` with `documentElement.clientWidth`, on every screen | This commit |

## 10. Safety before deploying (16 Oct)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 62 | Error | A plan request failed with a 500 when Token Factory was down (or the key was missing) | The notes-coverage call wasn't guarded | `safe_coverage` catches model errors, logs a warning, and returns no verdicts; every open term then pauses, with the reason "Couldn't check your notes just now". Tested live with the model URL pointed at a dead port: both learners' plans loaded | This commit |
| 63 | Error | Adding notes with the model down gave a 500 | Unhandled `openai.APIError` | A 503 with a clear message; the notes insert rolls back (checked: 0 rows before and after) | This commit |
| 64 | Decision | `DEMO_MODE=1` blocks new learners and notes on the public deploy | The API has no auth, and the notes endpoint spends the $1/day model budget | Both routes return 403; the setup screen shows a "Public demo" note instead of the form; `/api/config` tells the frontend. "I already know this" and events stay open (no model cost), and are cleared with the reset below | This commit |
| 65 | Decision | `python -m pipeline reset-demo` clears all events and every "I already know this" click, keeping notes and cached verdicts | Recordings and judges should start from the same state | A dry run unless `--yes`, because it deletes data | This commit (not run yet) |

## 11. Gemma for the novelty check (16 Oct)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 66 | Decision | The novelty check runs on Gemma-4-31B-IT (`NOVELTY_MODEL`); everything else stays on MiMo | Google DeepMind joined as a partner, with a $5,000 Gemma prize; the novelty check was the only stage with a fair test (20 labels, prompt frozen since 15 Oct) | Head to head on learner A: Gemma precision 0.46 / recall 0.60 in all 3 runs, against MiMo 0.50 / 0.60 (one extra false "known", within noise at n = 20). Gemma takes 9–11 s per call against MiMo's 103–210 s, gave identical verdicts every run, and costs about $0.00009 per call against $0.00036 | This commit |
| 67 | Hindrance | Gemma-4-31B-IT disappeared from Token Factory for part of 16 Oct (other teams saw the same), then came back | Model availability on Token Factory changes | A per-stage model with a fallback: `NOVELTY_MODEL`, then `LLM_MODEL`, then the offline path. `check-endpoint --model` probes any model | This commit |
| 68 | Decision | Gemma's price is derived from Token Factory's own bill: $0.035 / $0.079 per million input / output tokens | No published list price was found | Billed cost ÷ uncached tokens; the same method reproduces MiMo's list price exactly, so it's trustworthy. Labelled as derived in the code | This commit |
| 69 | Decision | MiMo's earlier verdicts for learner A were backed up before the experiment and replaced by Gemma's | The cache was the only copy of MiMo's verdicts | Backup kept outside the repo; restore only if we switch back | This commit |


## 12. Re-run and deploy image (16 Oct)

| # | Type | What happened / what was decided | Cause | Resolution | Status / commit |
|---|---|---|---|---|---|
| 70 | Decision | The lecture 2 clip was re-run as video 4 and old video 3 was deleted (its 2 events went with it; its 13 cost rows keep `video_id` NULL) | "colon equals" still paused (#23), and the deploy is seeded from one clean term set | A prompt line bans notation read aloud. Video 4: 21 terms, 42 quiz Qs, 0 chunks failed validation, no junk. "gradient descent algorithm" survives next to "gradient descent" (different chunks, cosine < 0.90); left in, because the mention ranking keeps it out of the 5 pauses. Learner A's video verdicts were cleared for a fresh Gemma check; 6 new terms need labels | This commit |
| 71 | Decision | Host: a Render web service (Free) plus Neon Postgres (Free) | HF Docker Spaces now need a paid plan; Fly.io has no free tier; Render's free Postgres expires after 30 days, which could fall inside judging. Neon has pgvector on every plan | Free tier sleeps after 15 min idle and takes about 1 min to wake; that's accepted for $0 | This commit |
| 72 | Decision | The image installs `requirements-serve.txt` only (no torch, Whisper or sentence-transformers) | With `DEMO_MODE=1` the app never embeds: new learners and notes are blocked, and "I already know this" copies the term's embedding in SQL. The heavy imports are lazy | Image 823 MB, clip included. Run with a 512 MB limit, `DEMO_MODE=1` and `$PORT`: health, index, plans for A and B, quiz, captions, video Range (206), dashboard and usage all answer; new learners and notes get 403; memory 58 MiB | This commit |
| 73 | Decision | One root Dockerfile: a Node 22 stage builds `frontend/dist`, and FastAPI serves it at `/` after the API routes | Decided 15 Oct: no web container. Vite 8 needs Node 20.19+ | `mount_frontend` mounts only if `index.html` exists, so dev and tests run without a build. The demo clip is baked into the image, because `data/` can't go in git; a second video would need object storage | This commit |
| 74 | Decision | Novelty eval on video 4 (learner A, Gemma-4-31B-IT, 7.6 s, 1,686 in / 278 out tokens): precision 0.50, recall 0.64, n = 21 | The re-run changed the term set; 6 new terms labelled before the model's output was seen | Same as #66 within one term (noise). Gemma judged 12 of 21 terms: 4 came from the questionnaire, and 5 reused this morning's video 3 verdicts, because covered verdicts are saved as `source='notes'` and only `source='video'` rows were cleared. Of the 11 disagreements, most are label definition (#29), not model error: labels answer "would I want a card", the model answers "do the notes cover the idea" (e.g. notes use `h_θ(x)` for hypothesis; local/global minimum and quadratic aren't in the notes at all). Not relabelled after seeing the output | This commit (label question still open) |
