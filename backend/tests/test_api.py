"""Endpoint tests against a real Postgres (see conftest.py); models are never called."""

import os

import psycopg
import pytest
from app.learner import OFFLINE
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)  # pretends to be a browser; no server needed


def sql(query: str, params: tuple = ()) -> list[tuple]:
    """Run SQL on the test database directly: set up a case, or check what an endpoint wrote."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []  # INSERTs return no rows


def stored_events() -> list[tuple]:
    return sql("SELECT learner_id, video_id, type, term_id, ts FROM events")


def test_videos_lists_only_processed_ones(db):
    videos = client.get("/api/videos").json()
    assert [v["id"] for v in videos] == [db["video"]]


def test_event_is_stored(db):
    event = {
        "learner_id": db["learner"],
        "video_id": db["video"],
        "type": "pause",
        "ts": 12.5,
    }
    assert client.post("/api/events", json=event).status_code == 200
    assert stored_events() == [(db["learner"], db["video"], "pause", None, 12.5)]


def test_event_with_unknown_type_is_rejected(db):
    event = {"learner_id": db["learner"], "video_id": db["video"], "type": "hack"}
    assert client.post("/api/events", json=event).status_code == 422
    assert stored_events() == []


def test_new_learner_gets_questionnaire_terms(db):
    topics = ["calculus", "linear_algebra", "probability", "ml_basics", "python"]
    answers = dict.fromkeys(topics, False) | {"calculus": True}
    response = client.post("/api/learners", json={"name": "Asha", "answers": answers})
    assert response.status_code == 200
    assert response.json()["seeded_terms"] == 4

    rows = sql(
        "SELECT term_text, source FROM learner_terms WHERE learner_id = %s ORDER BY term_text",
        (response.json()["learner_id"],),
    )
    terms = ["chain rule", "derivative", "gradient", "partial derivative"]
    assert rows == [(t, "questionnaire") for t in terms]


def get_plan(db) -> list[dict]:
    return client.get(f"/api/learners/{db['learner']}/videos/{db['video']}/plan").json()


def test_plan_skips_known_terms_and_pauses_on_new_ones(db):
    sql(
        "INSERT INTO learner_terms (learner_id, term_text, status, source)"
        " VALUES (%s, 'gradient descent', 'known', 'questionnaire')",
        (db["learner"],),
    )
    plan = [
        (p["term"], p["pause_ts"], p["status"], p["reason"], p["mentions"])
        for p in get_plan(db)
    ]
    assert plan == [  # in video order, with how often the transcript says each term
        ("gradient descent", 5, "known", "from your questionnaire", 2),
        ("learning rate", 22, "new", "not checked against notes", 1),
    ]


def test_plan_without_a_model_still_loads_and_says_so(db):
    sql(
        "INSERT INTO notes (learner_id, source, text) VALUES (%s, 'typed', 'my notes')",
        (db["learner"],),
    )
    reasons = {p["term"]: p["reason"] for p in get_plan(db)}
    # the learner has notes, but no model could check them: pause on everything, and say why
    assert reasons == {"gradient descent": OFFLINE, "learning rate": OFFLINE}


def mark_known(db, video_id: int, term_id: int):
    body = {"video_id": video_id, "term_id": term_id, "ts": 22.5}
    return client.post(f"/api/learners/{db['learner']}/known", json=body)


def test_i_know_this_updates_the_profile_and_logs_the_click(db):
    assert mark_known(db, db["video"], db["lr_term"]).status_code == 200
    profile = sql(
        "SELECT term_text, status, source FROM learner_terms WHERE learner_id = %s",
        (db["learner"],),
    )
    assert profile == [("learning rate", "known", "video")]
    assert stored_events() == [
        (db["learner"], db["video"], "known", db["lr_term"], 22.5)
    ]
    # what the learner sees next time: no more pause on that term
    status = {p["term"]: (p["status"], p["reason"]) for p in get_plan(db)}
    assert status["learning rate"] == ("known", "you marked it known")


def test_i_know_this_rejects_a_term_from_another_video(db):
    assert mark_known(db, db["unprocessed"], db["lr_term"]).status_code == 404
    assert sql("SELECT * FROM learner_terms") == []
    assert stored_events() == []  # the error rolled the whole request back


def test_usage_reports_cost_per_lecture_hour_and_per_learner(db):
    sql(
        "UPDATE videos SET duration_s = 1800 WHERE id = %s", (db["video"],)
    )  # a half-hour lecture
    costs = "INSERT INTO stage_costs (video_id, learner_id, stage, model, requests, input_tokens, output_tokens, retries_429, latency_ms) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    # processing the video (no learner): 1M in + 0.5M out on MiMo = $0.14 + $0.14 = $0.28
    sql(
        costs,
        (db["video"], None, "terms", "MiMo-V2.6-Flash", 3, 1_000_000, 500_000, 1, 2000),
    )
    # one learner's novelty check: 1M in on Gemma = $0.035
    sql(
        costs,
        (
            db["video"],
            db["learner"],
            "novelty",
            "Gemma-4-31B-IT",
            1,
            1_000_000,
            0,
            0,
            9000,
        ),
    )

    usage = client.get("/api/usage").json()
    assert usage["totals"]["requests"] == 4
    assert usage["totals"]["retries_429"] == 1
    # the README's headline number: $0.28 for half an hour is $0.56 per lecture hour
    assert usage["lecture"]["cost_per_hour_usd"] == pytest.approx(0.56)
    [learner] = usage["learners"]
    assert (learner["name"], learner["requests"]) == ("Test learner", 1)
    assert learner["cost_usd"] == pytest.approx(0.035)
    assert usage["quota"] == {"available": False, "reason": "faked in tests"}


def test_dashboard_ranks_the_term_learners_struggle_with_first(db):
    sql(
        "INSERT INTO learner_terms (learner_id, term_text, status, source) VALUES (%s, 'gradient descent', 'known', 'questionnaire')",
        (db["learner"],),
    )
    base = {
        "learner_id": db["learner"],
        "video_id": db["video"],
        "term_id": db["lr_term"],
    }
    client.post("/api/events", json=base | {"type": "pause", "ts": 22})
    client.post("/api/events", json=base | {"type": "quiz_answer", "correct": False})

    board = client.get(f"/api/dashboard/videos/{db['video']}").json()
    assert (
        board["sessions"],
        board["pauses"],
        board["quiz_answered"],
        board["quiz_correct"],
    ) == (1, 1, 1, 0)
    terms = [
        (t["term"], t["new_for"], t["paused"], t["wrong"], t["score"])
        for t in board["terms"]
    ]
    assert terms == [  # hardest first: score = learners who paused + wrong answers
        ("learning rate", 1, 1, 1, 2),
        ("gradient descent", 0, 0, 0, 0),
    ]
