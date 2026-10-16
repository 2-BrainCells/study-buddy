"""FastAPI serves the built frontend at / without hiding the API routes."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql://unused@localhost:1/none"
)  # main.py reads it at import

from app.main import mount_frontend
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_serves_index_and_keeps_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<h1>study buddy</h1>")
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    assert mount_frontend(app, tmp_path)
    client = TestClient(app)
    assert "study buddy" in client.get("/").text
    assert client.get("/api/ping").json() == {"ok": True}


def test_skips_mount_without_a_build(tmp_path):
    assert not mount_frontend(FastAPI(), tmp_path)
