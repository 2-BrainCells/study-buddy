"""Shared fixtures: a real Postgres for endpoint tests. Models are always faked."""

import os

import psycopg
import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")
# main.py reads DATABASE_URL at import, so set it before any test imports the app.
# Without a test database it points nowhere, so tests can never touch dev data.
os.environ["DATABASE_URL"] = TEST_DB or "postgresql://unused@localhost:1/none"


FAKE_QUOTA = {"available": False, "reason": "faked in tests"}


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Stand-in for BGE-M3: one 1024-dim vector per text. Not all zeros, since cosine of a zero vector is NaN."""
    return [[1.0] * 1024 for _ in texts]


@pytest.fixture
def db(monkeypatch):
    """Empty the test database, seed one lecture and one learner, and return the ids made."""
    if not TEST_DB:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL must be set in CI")
        pytest.skip("set TEST_DATABASE_URL to run database tests")

    # patch where it's used: learner.py imported embed by name, so swap app.learner's copy
    monkeypatch.setattr("app.learner.embed", fake_embed)
    # no Token Factory either: every endpoint takes its offline path
    monkeypatch.setattr("app.main.optional_token_factory", lambda: None)
    # nor its quota endpoint: main.py calls insights.cached_quota() through the module, so patch it there
    monkeypatch.setattr("app.insights.cached_quota", lambda: FAKE_QUOTA)

    with psycopg.connect(TEST_DB, autocommit=True) as conn:
        conn.execute("TRUNCATE videos, learners RESTART IDENTITY CASCADE")
        video_id = conn.execute(
            "INSERT INTO videos (title, source, licence, processed_at) VALUES ('A', 'B', 'C', now()) RETURNING id",
        ).fetchone()[0]
        unprocessed_id = conn.execute(
            "INSERT INTO videos (title, source, licence) VALUES ('A', 'B', 'C') RETURNING id",
        ).fetchone()[0]
        learner_id = conn.execute(
            "INSERT INTO learners (name) VALUES ('Test learner') RETURNING id",
        ).fetchone()[0]
        # a transcript that says "gradient descent" twice and "learning rate" once (the plan counts mentions)
        conn.execute(
            "INSERT INTO segments (video_id, start_s, end_s, text) VALUES (%s, 0, 30, %s)",
            (
                video_id,
                "We use gradient descent. Gradient descent needs a learning rate.",
            ),
        )
        gd_id, lr_id = (
            conn.execute(
                "INSERT INTO terms (video_id, term, first_ts, pause_ts, explanation)"
                " VALUES (%s, %s, %s, %s, 'An explanation.') RETURNING id",
                (video_id, term, ts, ts + 2),
            ).fetchone()[0]
            for term, ts in [("gradient descent", 3), ("learning rate", 20)]
        )
        yield {
            "video": video_id,
            "unprocessed": unprocessed_id,
            "learner": learner_id,
            "gd_term": gd_id,  # "gradient descent", pauses at 5 s
            "lr_term": lr_id,  # "learning rate", pauses at 22 s
        }
