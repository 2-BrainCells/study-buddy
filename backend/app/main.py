import hashlib
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

import openai
import psycopg
from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pipeline.llm import Settings, TokenFactory, db_cost_sink
from pipeline.transcribe import to_vtt
from pydantic import BaseModel

from app import insights
from app.learner import (
    SEED_TERMS,
    Questionnaire,
    add_known_terms,
    index_notes,
    video_plan,
)

DATABASE_URL = os.environ["DATABASE_URL"]
VIDEO_DIR = Path(os.environ.get("VIDEO_DIR", "../data/videos"))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", "../frontend/dist"))

app = FastAPI(title="Study Buddy")
api = APIRouter(prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Return ok only if the database answers; 503 otherwise."""
    try:
        # ponytail: new connection per call; add a pool when real endpoints exist
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as e:
        raise HTTPException(status_code=503, detail="database unavailable") from e
    return {"status": "ok"}


@lru_cache(maxsize=1)
def token_factory() -> TokenFactory:
    """One client per process, so the rate limiter is shared by all requests."""
    return TokenFactory(Settings.from_env(), db_cost_sink(DATABASE_URL))


class NewLearner(BaseModel):
    name: str
    answers: Questionnaire
    invite: str = ""


class Notes(BaseModel):
    text: str


class Known(BaseModel):
    video_id: int
    term_id: int
    ts: float


class Event(BaseModel):
    learner_id: int
    video_id: int
    type: Literal[
        "pause", "glance", "quiz_answer"
    ]  # validated here: this is a trust boundary
    term_id: int | None = None
    correct: bool | None = None
    ts: float | None = None


@api.get("/learners")
def list_learners() -> list[dict]:
    """Demo learners with their questionnaire answers and how many terms their notes added (for the profile strip).

    Real learners are private: their browser keeps their own details, so they're never listed here.
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT l.id, l.name, l.questionnaire,"
            " (SELECT count(*) FROM learner_terms lt WHERE lt.learner_id = l.id AND lt.source = 'notes')"
            " FROM learners l WHERE l.token_hash IS NULL ORDER BY l.id"
        ).fetchall()
    return [
        {"id": i, "name": n, "questionnaire": q or {}, "note_terms": c}
        for i, n, q, c in rows
    ]


def demo_mode() -> bool:
    """DEMO_MODE=1 on the public deploy: no new learners or notes, so strangers can't spend the model budget."""
    return os.environ.get("DEMO_MODE", "") == "1"


def hash_token(token: str) -> str:
    """SHA-256 of a learner token. Only the hash is stored, so a leaked database can't be used to log in."""
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(given: str | None, stored_hash: str) -> bool:
    """Whether the token a browser sent belongs to this learner. Timing-safe."""
    if not given:
        return False
    return secrets.compare_digest(hash_token(given), stored_hash)


def require_learner(learner_id: int, authorization: str | None) -> bool:
    """Allow a request on behalf of this learner, or raise 404/401. Returns True for a real (token) learner.

    Demo learners have no token_hash, so anyone may use them; everyone else must send
    "Authorization: Bearer <their token>".
    """
    # ponytail: one extra query per request; fold it into the endpoint's own connection if latency matters
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT token_hash FROM learners WHERE id = %s", (learner_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "learner not found")
    if row[0] is None:
        return False
    given = authorization.removeprefix("Bearer ") if authorization else None
    if not token_matches(given, row[0]):
        raise HTTPException(401, "This learner's token is missing or wrong.")
    return True


def require_not_demo() -> None:
    if demo_mode():
        raise HTTPException(403, "Adding learners and notes is turned off in the public demo.")


def optional_token_factory() -> TokenFactory | None:
    """The model client, or None when its settings are missing (the app then runs from cached data)."""
    try:
        return token_factory()
    except KeyError:
        return None


@api.get("/config")
def get_config() -> dict:
    """What the frontend needs to know about this deployment: demo mode, and whether sign-up takes an invite code."""
    return {"demo": demo_mode(), "invite": bool(os.environ.get("INVITE_CODE"))}


def require_invite(given: str) -> None:
    """With INVITE_CODE set, sign-up needs it (this is how classmates get in on the public demo).
    Without it, demo mode decides."""
    code = os.environ.get("INVITE_CODE")
    if not code:
        require_not_demo()
        return
    # bytes, not str: compare_digest raises TypeError on non-ASCII text (e.g. a typed "café")
    if not secrets.compare_digest(given.encode(), code.encode()):
        raise HTTPException(403, "That invite code isn't right.")


@api.post("/learners")
def create_learner(body: NewLearner) -> dict:
    """Create a learner and seed the profile from the questionnaire."""
    require_invite(body.invite)
    token = secrets.token_urlsafe(32)  # returned once, below; only its hash is stored
    with psycopg.connect(DATABASE_URL) as conn:
        learner_id = conn.execute(
            "INSERT INTO learners (name, questionnaire, token_hash) VALUES (%s, %s, %s) RETURNING id",
            (body.name, body.answers.model_dump_json(), hash_token(token)),
        ).fetchone()[0]
        seeds = [
            t
            for topic, yes in body.answers.model_dump().items()
            if yes
            for t in SEED_TERMS[topic]
        ]
        seeded = add_known_terms(conn, learner_id, seeds, "questionnaire")
    return {"learner_id": learner_id, "seeded_terms": seeded, "token": token}


def warm_plans(learner_id: int) -> None:
    """Run the slow notes-coverage call now (100-210 s), so the player's GET /plan is a cache hit."""
    # ponytail: a GET /plan during warm-up makes its own LLM call; add a per-learner lock if that bites
    with psycopg.connect(DATABASE_URL) as conn:
        video_ids = [
            v
            for (v,) in conn.execute(
                "SELECT id FROM videos WHERE processed_at IS NOT NULL"
            )
        ]
    for video_id in (
        video_ids
    ):  # one connection per video, so one failure doesn't roll back the others
        with psycopg.connect(DATABASE_URL) as conn:
            video_plan(conn, optional_token_factory(), learner_id, video_id)


@api.post("/learners/{learner_id}/notes")
def add_notes(learner_id: int, body: Notes, background: BackgroundTasks, authorization: str | None = Header(None)) -> dict:
    """Index typed notes into the learner's profile, then precompute their video plans in the background."""
    if not require_learner(learner_id, authorization):
        require_not_demo()  # demo learners are shared, so the public demo keeps them read-only
    tf = optional_token_factory()
    if tf is None:
        raise HTTPException(503, "Reading notes needs the model, which isn't configured.")
    try:
        with psycopg.connect(DATABASE_URL) as conn:  # rolled back on error, so no half-indexed notes
            added = index_notes(conn, tf, learner_id, body.text)
    except openai.APIError as e:
        raise HTTPException(503, "The model is unavailable right now; try adding notes again later.") from e
    background.add_task(warm_plans, learner_id)
    return {"terms_added": added}


@api.get("/learners/{learner_id}/videos/{video_id}/plan")
def get_plan(learner_id: int, video_id: int, authorization: str | None = Header(None)) -> list[dict]:
    """This learner's pause plan for one video."""
    require_learner(learner_id, authorization)
    with psycopg.connect(DATABASE_URL) as conn:
        return video_plan(conn, optional_token_factory(), learner_id, video_id)


@api.post("/learners/{learner_id}/known")
def mark_known(learner_id: int, body: Known, authorization: str | None = Header(None)) -> dict:
    """'I already know this': the term becomes known for this learner, and the click is logged."""
    require_learner(learner_id, authorization)
    with psycopg.connect(DATABASE_URL) as conn:
        cur = conn.execute(
            "INSERT INTO learner_terms (learner_id, term_text, embedding, status, source)"
            " SELECT %s, lower(term), embedding, 'known', 'video' FROM terms WHERE id = %s AND video_id = %s"
            " ON CONFLICT (learner_id, term_text) DO UPDATE SET status = 'known', updated_at = now()",
            (learner_id, body.term_id, body.video_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "term not in this video")
        conn.execute(
            "INSERT INTO events (learner_id, video_id, type, term_id, ts) VALUES (%s, %s, 'known', %s, %s)",
            (learner_id, body.video_id, body.term_id, body.ts),
        )
    return {"ok": True}


@api.post("/events")
def log_event(e: Event, authorization: str | None = Header(None)) -> dict:
    require_learner(e.learner_id, authorization)  # events feed the case study, so nobody can fake another's
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO events (learner_id, video_id, type, term_id, correct, ts) VALUES (%s, %s, %s, %s, %s, %s)",
            (e.learner_id, e.video_id, e.type, e.term_id, e.correct, e.ts),
        )
    return {"ok": True}


@api.get("/videos")
def list_videos() -> list[dict]:
    """Processed videos, with the source and licence the player must credit."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT id, title, source, licence, duration_s FROM videos WHERE processed_at IS NOT NULL ORDER BY id"
        ).fetchall()
    return [
        dict(zip(("id", "title", "source", "licence", "duration_s"), r)) for r in rows
    ]


@api.get("/videos/{video_id}/media")
def video_media(video_id: int) -> FileResponse:
    """The lecture file. FileResponse answers Range requests, so the player can seek."""
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT file FROM videos WHERE id = %s", (video_id,)
        ).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, "video not found")
    path = VIDEO_DIR / row[0]
    if not path.is_file():
        raise HTTPException(404, f"video file missing: {row[0]}")
    return FileResponse(path, media_type="video/mp4")


@api.get("/videos/{video_id}/captions.vtt")
def captions(video_id: int) -> Response:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT start_s, end_s, text FROM segments WHERE video_id = %s ORDER BY start_s",
            (video_id,),
        ).fetchall()
    return Response(to_vtt(rows), media_type="text/vtt")


@api.get("/videos/{video_id}/quiz")
def quiz(video_id: int) -> list[dict]:
    """All cached questions; the player picks 5."""
    # ponytail: answers go to the browser; fine for self-study, check answers server-side if quizzes ever count
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT id, term_id, question, options, answer FROM quiz_questions WHERE video_id = %s ORDER BY id",
            (video_id,),
        ).fetchall()
    return [
        dict(zip(("id", "term_id", "question", "options", "answer"), r)) for r in rows
    ]


@api.get("/usage")
def get_usage() -> dict:
    """AMD usage panel: requests, tokens, latency and cost per stage, per lecture hour and per learner, plus quota."""
    with psycopg.connect(DATABASE_URL) as conn:
        return insights.usage(conn, insights.cached_quota())


@api.get("/dashboard/videos/{video_id}")
def get_dashboard(video_id: int) -> dict:
    """Ed-tech dashboard: where learners struggle in one video."""
    with psycopg.connect(DATABASE_URL) as conn:
        return insights.dashboard(conn, video_id)


def mount_frontend(target: FastAPI, dist: Path) -> bool:
    """Serve the built React app at / if it exists; dev and tests run without it. Returns whether it mounted."""
    if not (dist / "index.html").exists():
        return False
    target.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


app.include_router(api)  # last: it copies the routes that exist at this point
mount_frontend(app, FRONTEND_DIST)  # after the API: a mount at / matches every path
