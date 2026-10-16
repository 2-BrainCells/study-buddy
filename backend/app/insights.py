"""Ed-tech dashboard and AMD usage panel: read-only aggregates over events, learner_terms and stage_costs."""

import time

from pipeline.llm import Settings, quota_summary, rate_limits

# USD per million (input, output) tokens at Token Factory list price, checked 14 Oct. Models without a price
# show cost as None ("n/a"), never a guess. Token Factory's own bill is lower when prompt caching hits.
PRICES = {
    "MiMo-V2.6-Flash": (0.14, 0.28),
    # derived 16 Oct from Token Factory's own bill (uncached input tokens; the same method reproduces MiMo's list price)
    "Gemma-4-31B-IT": (0.035, 0.079),
}
QUOTA_TTL_S = 60


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """List-price cost of some tokens, or None when the model has no known price (e.g. CPU stages)."""
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


def per_hour(value: float, duration_s: float | None) -> float | None:
    """Scale a per-video amount to one hour of lecture."""
    return value * 3600 / duration_s if duration_s else None


def struggle_rows(rows: list[tuple], learners: int) -> list[dict]:
    """Per-term dashboard rows, hardest first. Score = paused + wrong answers (a simple heuristic, not validated)."""
    out = []
    for (
        term_id,
        term,
        pause_ts,
        known_by,
        paused,
        marked_known,
        answered,
        wrong,
    ) in rows:
        out.append(
            {
                "term_id": term_id,
                "term": term,
                "pause_ts": pause_ts,
                "new_for": max(learners - known_by, 0),
                "paused": paused,
                "marked_known": marked_known,
                "answered": answered,
                "wrong": wrong,
                "score": paused + wrong,
            }
        )
    return sorted(out, key=lambda r: (-r["score"], r["pause_ts"]))


TERMS_SQL = """
SELECT t.id, t.term, t.pause_ts,
       (SELECT count(*) FROM learner_terms lt WHERE lt.term_text = lower(t.term) AND lt.status = 'known'),
       count(DISTINCT e.learner_id) FILTER (WHERE e.type IN ('pause', 'glance')),
       count(e.id) FILTER (WHERE e.type = 'known'),
       count(e.id) FILTER (WHERE e.type = 'quiz_answer'),
       count(e.id) FILTER (WHERE e.type = 'quiz_answer' AND NOT e.correct)
FROM terms t LEFT JOIN events e ON e.term_id = t.id
WHERE t.video_id = %s
GROUP BY t.id
"""


def dashboard(conn, video_id: int) -> dict:
    """Where learners struggle in one video, from real events only."""
    learners = conn.execute("SELECT count(*) FROM learners").fetchone()[0]
    sessions, pauses, answered, correct = conn.execute(
        "SELECT count(DISTINCT learner_id), count(*) FILTER (WHERE type = 'pause'),"
        " count(*) FILTER (WHERE type = 'quiz_answer'), count(*) FILTER (WHERE type = 'quiz_answer' AND correct)"
        " FROM events WHERE video_id = %s",
        (video_id,),
    ).fetchone()
    return {
        "learners": learners,
        "sessions": sessions,
        "pauses": pauses,
        "quiz_answered": answered,
        "quiz_correct": correct,
        "terms": struggle_rows(
            conn.execute(TERMS_SQL, (video_id,)).fetchall(), learners
        ),
    }


def usage(conn, quota: dict) -> dict:
    """What the AMD models (and the CPU stages) did, and what it cost, from stage_costs."""
    stages = []
    for stage, model, req, tin, tout, r429, avg_ms, max_ms in conn.execute(
        "SELECT stage, model, sum(requests), sum(input_tokens), sum(output_tokens), sum(retries_429),"
        " avg(latency_ms), max(latency_ms) FROM stage_costs GROUP BY stage, model ORDER BY stage"
    ):
        stages.append(
            {
                "stage": stage,
                "model": model,
                "requests": req,
                "input_tokens": tin,
                "output_tokens": tout,
                "retries_429": r429,
                "avg_latency_ms": round(avg_ms),
                "max_latency_ms": max_ms,
                "cost_usd": cost_usd(model, tin, tout),
            }
        )
    totals = {
        k: sum(s[k] for s in stages)
        for k in ("requests", "input_tokens", "output_tokens", "retries_429")
    } | {"cost_usd": sum(s["cost_usd"] or 0 for s in stages)}

    lecture = None
    video = conn.execute(
        "SELECT id, title, duration_s FROM videos WHERE processed_at IS NOT NULL ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    if video:
        vid, title, duration = video
        rows = conn.execute(
            "SELECT model, sum(input_tokens), sum(output_tokens) FROM stage_costs"
            " WHERE video_id = %s AND learner_id IS NULL GROUP BY model",
            (vid,),
        ).fetchall()
        tokens = sum(tin + tout for _, tin, tout in rows)
        cost = sum(cost_usd(m, tin, tout) or 0 for m, tin, tout in rows)
        lecture = {
            "video_id": vid,
            "title": title,
            "duration_s": duration,
            "tokens": tokens,
            "cost_usd": cost,
            "tokens_per_hour": per_hour(tokens, duration),
            "cost_per_hour_usd": per_hour(cost, duration),
        }

    per_learner: dict[int, dict] = {}
    for lid, name, model, req, tin, tout in conn.execute(
        "SELECT s.learner_id, l.name, s.model, sum(s.requests), sum(s.input_tokens), sum(s.output_tokens)"
        " FROM stage_costs s JOIN learners l ON l.id = s.learner_id GROUP BY s.learner_id, l.name, s.model"
    ):
        row = per_learner.setdefault(
            lid,
            {
                "learner_id": lid,
                "name": name,
                "requests": 0,
                "tokens": 0,
                "cost_usd": 0.0,
            },
        )
        row["requests"] += req
        row["tokens"] += tin + tout
        row["cost_usd"] += cost_usd(model, tin, tout) or 0

    return {
        "stages": stages,
        "totals": totals,
        "lecture": lecture,
        "learners": list(per_learner.values()),
        "quota": quota,
    }


_quota: dict = {"at": float("-inf"), "value": None}


def cached_quota() -> dict:
    """Token Factory quota, fetched at most once a minute. Never raises (missing env is a safe default too)."""
    now = time.monotonic()
    if now - _quota["at"] > QUOTA_TTL_S:
        try:
            settings = Settings.from_env()
        except KeyError as e:
            value = {"available": False, "reason": f"missing env var {e}"}
        else:
            value = quota_summary(rate_limits(settings))
        _quota.update(at=now, value=value)
    return _quota["value"]
