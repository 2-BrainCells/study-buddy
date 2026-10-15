import os
from functools import lru_cache

import psycopg
from fastapi import FastAPI, HTTPException
from pipeline.llm import Settings, TokenFactory, db_cost_sink
from pydantic import BaseModel

from app.learner import (
    SEED_TERMS,
    Questionnaire,
    add_known_terms,
    index_notes,
    video_plan,
)

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="Study Buddy")


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


class Notes(BaseModel):
    text: str


@app.post("/learners")
def create_learner(body: NewLearner) -> dict:
    """Create a learner and seed the profile from the questionnaire."""
    with psycopg.connect(DATABASE_URL) as conn:
        learner_id = conn.execute(
            "INSERT INTO learners (name, questionnaire) VALUES (%s, %s) RETURNING id",
            (body.name, body.answers.model_dump_json()),
        ).fetchone()[0]
        seeds = [
            t
            for topic, yes in body.answers.model_dump().items()
            if yes
            for t in SEED_TERMS[topic]
        ]
        seeded = add_known_terms(conn, learner_id, seeds, "questionnaire")
    return {"learner_id": learner_id, "seeded_terms": seeded}


@app.post("/learners/{learner_id}/notes")
def add_notes(learner_id: int, body: Notes) -> dict:
    """Index typed notes into the learner's profile."""
    with psycopg.connect(DATABASE_URL) as conn:
        added = index_notes(conn, token_factory(), learner_id, body.text)
    return {"terms_added": added}


@app.get("/learners/{learner_id}/videos/{video_id}/plan")
def get_plan(learner_id: int, video_id: int) -> list[dict]:
    """This learner's pause plan for one video."""
    with psycopg.connect(DATABASE_URL) as conn:
        return video_plan(conn, token_factory(), learner_id, video_id)
