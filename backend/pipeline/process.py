"""python -m pipeline process <video>: transcript -> terms -> embeddings -> Postgres."""

import os
import random
import statistics
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from sentence_transformers import SentenceTransformer

from pipeline.llm import Settings, StageCost, TokenFactory, db_cost_sink
from pipeline.terms import chunk, extract_terms, place, shuffle_options
from pipeline.transcribe import WHISPER_MODEL, transcribe

EMBED_MODEL = "BAAI/bge-m3"
SOURCE = "Stanford Engineering Everywhere, CS229 (Andrew Ng)"
LICENCE = "CC BY-NC-SA 4.0"


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def to_vector(v) -> str:
    """pgvector text format: '[0.1,0.2,...]' (avoids adding the pgvector package)."""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def process(video: Path, title: str) -> None:
    """Run the per-video pipeline once and cache everything in Postgres."""
    db = os.environ["DATABASE_URL"]
    sink = db_cost_sink(db)

    with psycopg.connect(db) as conn:  # committed now so cost rows can reference it
        conn.execute("DELETE FROM videos WHERE title = %s", (title,))
        video_id = conn.execute(
            "INSERT INTO videos (title, source, licence) VALUES (%s, %s, %s) RETURNING id",
            (title, SOURCE, LICENCE),
        ).fetchone()[0]

    segments, duration, transcribe_ms = transcribe(video)
    sink(
        StageCost(
            stage="transcribe",
            model=f"faster-whisper-{WHISPER_MODEL}",
            requests=1,
            input_tokens=0,
            output_tokens=0,
            retries_429=0,
            latency_ms=transcribe_ms,
            video_id=video_id,
        )
    )

    words = [w for s in segments for w in s.words]
    chunks = chunk(words)
    tf = TokenFactory(
        Settings.from_env(), sink, max_tokens=4000
    )  # 8 terms x 2 quiz Qs needs >2000
    terms, failed = extract_terms(tf, chunks, video_id)
    placed = [(t, place(t.term, words)) for t in terms]
    kept = [(t, p) for t, p in placed if p]

    t0 = time.monotonic()
    vectors = SentenceTransformer(EMBED_MODEL, device="cpu").encode(
        [t.term for t, _ in kept], normalize_embeddings=True
    )
    sink(
        StageCost(
            stage="embed",
            model=EMBED_MODEL,
            requests=1,
            input_tokens=0,
            output_tokens=0,
            retries_429=0,
            latency_ms=_ms(t0),
            video_id=video_id,
        )
    )

    rng = random.Random(video_id)  # reproducible shuffles
    with psycopg.connect(db) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO segments (video_id, start_s, end_s, text) VALUES (%s, %s, %s, %s)",
                [(video_id, s.start, s.end, s.text) for s in segments],
            )
        for (t, (first, pause)), vec in zip(kept, vectors):
            term_id = conn.execute(
                "INSERT INTO terms (video_id, term, first_ts, pause_ts, explanation, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id",
                (video_id, t.term, first, pause, t.explanation, to_vector(vec)),
            ).fetchone()[0]
            for q in t.quiz:
                options, answer = shuffle_options(q, rng)
                conn.execute(
                    "INSERT INTO quiz_questions (video_id, term_id, question, options, answer)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (video_id, term_id, q.question, Jsonb(options), answer),
                )
        conn.execute(
            "UPDATE videos SET duration_s = %s, processed_at = now() WHERE id = %s",
            (duration, video_id),
        )

    delays = [p - f for _, (f, p) in kept] or [0.0]
    print(
        f"video {video_id}: {duration / 60:.1f} min, {len(segments)} segments, {len(chunks)} chunks "
        f"({failed} failed validation)"
    )
    print(
        f"terms: {len(terms)} found, {len(kept)} placed, {len(terms) - len(kept)} not found in transcript; "
        f"{2 * len(kept)} quiz questions"
    )
    print(
        f"pause delay after first mention: median {statistics.median(delays):.1f}s, max {max(delays):.1f}s"
    )
