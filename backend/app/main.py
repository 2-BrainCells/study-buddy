import os

import psycopg
from fastapi import FastAPI, HTTPException

DATABASE_URL = os.environ['DATABASE_URL']

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
    