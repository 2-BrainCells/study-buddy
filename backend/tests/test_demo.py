"""Demo mode keeps the public deploy from spending the model budget (no database or model calls)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused@localhost:1/none")  # main.py reads it at import

from app.learner import reset_sessions
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
LEARNER = {"name": "x", "answers": dict.fromkeys(["calculus", "linear_algebra", "probability", "ml_basics", "python"], False)}


def test_demo_mode_blocks_new_learners(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.delenv("INVITE_CODE", raising=False)
    assert client.get("/api/config").json() == {"demo": True, "invite": False}
    assert client.post("/api/learners", json=LEARNER).status_code == 403
    # notes now depend on who the learner is (demo or real), so that check needs the database: see test_api.py


def test_config_reports_demo_off_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("INVITE_CODE", raising=False)
    assert client.get("/api/config").json() == {"demo": False, "invite": False}


def test_config_reports_invites(monkeypatch):
    monkeypatch.setenv("INVITE_CODE", "letmein")
    assert client.get("/api/config").json()["invite"] is True  # never the code itself


class FakeConn:
    """Answers the two counts and records statements, standing in for a psycopg connection."""

    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql, *args):
        self.statements.append(sql)
        return self

    def fetchone(self):
        return (3,)


def test_reset_is_a_dry_run_unless_asked():
    conn = FakeConn()
    assert reset_sessions(conn) == {"events": 3, "known_clicks": 3}
    assert not any(s.startswith("DELETE") for s in conn.statements)
    reset_sessions(conn, dry_run=False)
    assert sum(s.startswith("DELETE") for s in conn.statements) == 2
