"""Endpoint tests against a real Postgres (see conftest.py); models are never called."""

import os

import psycopg
import pytest
from app.learner import OFFLINE
from app.main import app, hash_token
from fastapi.testclient import TestClient

client = TestClient(app)  # pretends to be a browser; no server needed
TOPICS = ["calculus", "linear_algebra", "probability", "ml_basics", "python"]


def signup(invite: str = ""):
    """POST a new learner who is only comfortable with calculus."""
    answers = dict.fromkeys(TOPICS, False) | {"calculus": True}
    return client.post(
        "/api/learners", json={"name": "Asha", "answers": answers, "invite": invite}
    )


def test_signup_with_wrong_invite_is_refused(db, monkeypatch):
    monkeypatch.setenv("INVITE_CODE", "letmein")
    assert signup(invite="nope").status_code == 403
    assert signup().status_code == 403  # no code at all
    assert sql("SELECT count(*) FROM learners") == [(1,)]  # only the fixture's learner


def test_signup_with_invite_returns_a_token_stored_only_as_a_hash(db, monkeypatch):
    monkeypatch.setenv("INVITE_CODE", "letmein")
    response = signup(invite="letmein")
    assert response.status_code == 200
    token = response.json()["token"]
    [(stored,)] = sql(
        "SELECT token_hash FROM learners WHERE id = %s",
        (response.json()["learner_id"],),
    )
    assert stored == hash_token(token)
    assert stored != token  # the token itself is never stored


def test_signup_with_non_ascii_invite_is_refused_not_a_crash(db, monkeypatch):
    monkeypatch.setenv("INVITE_CODE", "letmein")
    assert (
        signup(invite="café").status_code == 403
    )  # compare_digest on str would raise TypeError (a 500)


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
    response = signup()  # no INVITE_CODE set: local dev stays open
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


# The fixture's learner is a public demo learner (no token), which is why every test above needs no header.


def real_learner() -> tuple[int, dict]:
    """Sign up a real learner; returns their id and the header that proves it's them."""
    body = signup().json()
    return body["learner_id"], {"Authorization": f"Bearer {body['token']}"}


def test_a_real_learners_plan_needs_their_own_token(db):
    lid, me = real_learner()
    _, someone_else = real_learner()
    url = f"/api/learners/{lid}/videos/{db['video']}/plan"
    assert client.get(url).status_code == 401  # no token
    assert client.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get(url, headers=someone_else).status_code == 401
    )  # a real token, but not theirs
    assert client.get(url, headers=me).status_code == 200
    assert client.get(f"/api/learners/999/videos/{db['video']}/plan").status_code == 404


def test_nobody_can_click_or_log_events_as_someone_else(db):
    lid, me = real_learner()
    known = {"video_id": db["video"], "term_id": db["lr_term"], "ts": 22.5}
    event = {"learner_id": lid, "video_id": db["video"], "type": "pause"}
    assert client.post(f"/api/learners/{lid}/known", json=known).status_code == 401
    assert client.post("/api/events", json=event).status_code == 401
    assert stored_events() == []  # the case-study data stays clean
    assert (
        client.post(f"/api/learners/{lid}/known", json=known, headers=me).status_code
        == 200
    )
    assert client.post("/api/events", json=event, headers=me).status_code == 200
    assert len(stored_events()) == 2  # the known click and the pause


def test_public_demo_keeps_demo_learners_read_only_but_real_learners_can_add_notes(
    db, monkeypatch
):
    lid, me = real_learner()
    monkeypatch.setenv("DEMO_MODE", "1")
    notes = {"text": "my notes"}
    assert (
        client.post(f"/api/learners/{db['learner']}/notes", json=notes).status_code
        == 403
    )
    # a real learner gets past the demo gate; the 503 is only because tests have no model
    assert (
        client.post(f"/api/learners/{lid}/notes", json=notes, headers=me).status_code
        == 503
    )


def test_learner_list_shows_only_demo_learners(db):
    real_learner()  # signs up "Asha"
    names = [learner["name"] for learner in client.get("/api/learners").json()]
    assert names == ["Test learner"]


def test_usage_panel_never_shows_a_real_learners_name(db):
    lid, _ = real_learner()
    for learner_id in (db["learner"], lid):
        sql(
            "INSERT INTO stage_costs (video_id, learner_id, stage, model, requests, input_tokens, output_tokens,"
            " retries_429, latency_ms) VALUES (%s, %s, 'novelty', 'Gemma-4-31B-IT', 1, 100, 10, 0, 900)",
            (db["video"], learner_id),
        )
    rows = client.get("/api/usage").json()["learners"]
    names = {row["learner_id"]: row["name"] for row in rows}
    assert names == {
        db["learner"]: "Test learner",
        lid: f"Learner {lid}",
    }  # never "Asha"
