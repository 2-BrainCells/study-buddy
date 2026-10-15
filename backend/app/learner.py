"""Learner profile (questionnaire + notes) and the per-video novelty check."""

import logging

import openai
import pydantic
from pipeline.embed import embed, to_vector
from pipeline.llm import EmptyReplyError, TokenFactory
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)
# what Token Factory can fail with after its own retries: network/HTTP errors, a reply that breaks the schema, empty
MODEL_ERRORS = (openai.APIError, pydantic.ValidationError, EmptyReplyError)
OFFLINE = "notes check unavailable"

SEED_TERMS = {
    "calculus": ["derivative", "partial derivative", "chain rule", "gradient"],
    "linear_algebra": ["vector", "matrix", "transpose", "dot product"],
    "probability": [
        "probability",
        "random variable",
        "expected value",
        "gaussian distribution",
    ],
    "ml_basics": [
        "linear regression",
        "cost function",
        "gradient descent",
        "training set",
    ],
    "python": ["python", "numpy"],
}


class Questionnaire(BaseModel):
    """The 5 onboarding questions: 'Are you comfortable with ...?'"""

    calculus: bool
    linear_algebra: bool
    probability: bool
    ml_basics: bool
    python: bool


class NoteTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[str]


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str
    covered: bool
    evidence: str  # up to 15 words from the notes; "" when not covered


class CoverageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdicts: list[Verdict]


NOTES_PROMPT = """These are a learner's own study notes. List the technical terms the notes show the learner has studied.
Copy each term as written in the notes. Skip everyday words.

Notes:
"""

COVERAGE_PROMPT = """Below are a learner's own study notes and terms from a lecture they are about to watch.
For EACH term, decide whether the notes show the learner has already studied that idea.
- covered = true if the notes explain or use the idea, even under another name or only as a formula
  or symbol (for example, a formula for 1/(1+e^-z) covers "logistic function").
- covered = false if the notes only touch a related topic.
- evidence: up to 15 words from the notes that show it, or "" when covered is false.
Return one verdict per term, copying each term exactly.

Terms:
{terms}

Notes:
{notes}
"""


def chunk_text(text: str, size: int = 600) -> list[str]:
    """Pack paragraphs into chunks of about `size` words (one LLM call each)."""
    chunks: list[str] = []
    current: list[str] = []
    for para in text.split("\n\n"):
        current.append(para)
        if sum(len(p.split()) for p in current) >= size:
            chunks.append("\n\n".join(current))
            current = []
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def check_coverage(
    tf: TokenFactory, notes: str, terms: list[str], learner_id: int, video_id: int
) -> dict[str, Verdict]:
    """One LLM call: which video terms do the learner's notes already cover? Keys are lowercased terms."""
    if not notes.strip() or not terms:
        return {}
    # ponytail: sends all notes in one call; chunk or retrieve top notes when they pass ~6k words
    prompt = COVERAGE_PROMPT.format(
        terms="\n".join(f"- {t}" for t in terms), notes=notes
    )
    out = tf.chat_json(
        "novelty",
        CoverageOut,
        [{"role": "user", "content": prompt}],
        learner_id=learner_id,
        video_id=video_id,
    )
    return {v.term.strip().lower(): v for v in out.verdicts}


def safe_coverage(
    tf: TokenFactory | None, notes: str, terms: list[str], learner_id: int, video_id: int
) -> tuple[dict[str, Verdict], bool]:
    """check_coverage, but a missing or failing model gives ({}, False) instead of an error.

    The player then pauses on every term not in the profile, which is the safe side for a learner.
    """
    if tf is None:
        return {}, False
    try:
        return check_coverage(tf, notes, terms, learner_id, video_id), True
    except MODEL_ERRORS as e:
        log.warning("notes coverage check failed for learner %s video %s: %s", learner_id, video_id, e)
        return {}, False


KNOWN_BECAUSE = {"questionnaire": "from your questionnaire", "notes": "in your notes", "video": "you marked it known"}


def classify(
    term: str, profile: dict[str, tuple[str, str]], verdicts: dict[str, Verdict], checked: bool = True
) -> tuple[str, str]:
    """Return (status, reason): the learner's profile (status, source) first, then the notes-coverage verdict."""
    key = term.lower()
    if key in profile:
        status, source = profile[key]
        # profile rows marked new only come from cached notes verdicts
        return ("known", KNOWN_BECAUSE.get(source, source)) if status == "known" else ("new", "not in notes")
    v = verdicts.get(key)
    if v is None:
        # no notes, the LLM skipped the term, or the model was unreachable: visible, not hidden
        return "new", ("not checked against notes" if checked else OFFLINE)
    return ("known", f"notes: {v.evidence}") if v.covered else ("new", "not in notes")


def add_known_terms(conn, learner_id: int, terms: list[str], source: str) -> int:
    """Embed terms and add them to the profile as known; existing entries win. Returns rows added."""
    terms = sorted({t.strip().lower() for t in terms if t.strip()})
    if not terms:
        return 0
    added = 0
    for term, vec in zip(terms, embed(terms)):
        cur = conn.execute(
            "INSERT INTO learner_terms (learner_id, term_text, embedding, status, source)"
            " VALUES (%s, %s, %s::vector, 'known', %s) ON CONFLICT (learner_id, term_text) DO NOTHING",
            (learner_id, term, to_vector(vec), source),
        )
        added += cur.rowcount
    return added


def index_notes(conn, tf: TokenFactory, learner_id: int, text: str) -> int:
    """Store typed notes, ask the LLM which terms they cover, add those to the profile."""
    # new notes can change coverage verdicts, so drop the cached ones
    conn.execute(
        "DELETE FROM learner_terms WHERE learner_id = %s AND source = 'video' AND status = 'new'",
        (learner_id,),
    )
    conn.execute(
        "INSERT INTO notes (learner_id, source, status, text) VALUES (%s, 'typed', 'reviewed', %s)",
        (learner_id, text),
    )
    terms: list[str] = []
    for chunk in chunk_text(text):
        out = tf.chat_json(
            "notes_terms",
            NoteTerms,
            [{"role": "user", "content": NOTES_PROMPT + chunk}],
            learner_id=learner_id,
        )
        terms += out.terms
    return add_known_terms(conn, learner_id, terms, "notes")


# mentions: how often the transcript says the term, a rough importance signal for choosing which stops pause
# ponytail: plain substring count; "parameters" also counts inside "parameters theta". Fine for ranking.
PLAN_SQL = """
WITH tx AS (
    SELECT lower(coalesce(string_agg(text, ' ' ORDER BY start_s), '')) AS t FROM segments WHERE video_id = %(vid)s
)
SELECT t.id, t.term, t.pause_ts, t.explanation, nn.term_text, nn.sim,
       (length(tx.t) - length(replace(tx.t, lower(t.term), ''))) / greatest(length(t.term), 1) AS mentions
FROM terms t
CROSS JOIN tx
LEFT JOIN LATERAL (
    SELECT lt.term_text, 1 - (lt.embedding <=> t.embedding) AS sim
    FROM learner_terms lt
    WHERE lt.learner_id = %(lid)s AND lt.status = 'known' AND lt.embedding IS NOT NULL
    ORDER BY lt.embedding <=> t.embedding
    LIMIT 1
) nn ON true
WHERE t.video_id = %(vid)s
ORDER BY t.pause_ts
"""

# covered terms are stored as source 'notes' (the notes cover them); not-covered ones as 'video'
# ponytail: the evidence quote is only shown on the first load; add an evidence column if the card needs it
SAVE_VERDICT = """
INSERT INTO learner_terms (learner_id, term_text, embedding, status, source)
SELECT %s, lower(term), embedding, %s, %s FROM terms WHERE id = %s
ON CONFLICT (learner_id, term_text) DO NOTHING
"""


def video_plan(conn, tf: TokenFactory | None, learner_id: int, video_id: int) -> list[dict]:
    """Every term in the video with this learner's status, the reason, and the closest known term."""
    profile = {
        term: (status, source)
        for term, status, source in conn.execute(
            "SELECT term_text, status, source FROM learner_terms WHERE learner_id = %s", (learner_id,)
        )
    }
    notes = conn.execute(
        "SELECT coalesce(string_agg(text, ' '), '') FROM notes WHERE learner_id = %s",
        (learner_id,),
    ).fetchone()[0]
    rows = conn.execute(PLAN_SQL, {"lid": learner_id, "vid": video_id}).fetchall()

    pending = [(tid, term) for tid, term, *_ in rows if term.lower() not in profile]
    verdicts, checked = safe_coverage(tf, notes, [t for _, t in pending], learner_id, video_id)
    checked = checked or not notes.strip()  # with no notes there was nothing to check
    for tid, term in pending:
        if (v := verdicts.get(term.lower())) is not None:
            status, source = ("known", "notes") if v.covered else ("new", "video")
            conn.execute(SAVE_VERDICT, (learner_id, status, source, tid))

    plan = []
    for term_id, term, pause_ts, explanation, nearest, sim, mentions in rows:
        status, reason = classify(term, profile, verdicts, checked)
        plan.append(
            {
                "term_id": term_id,
                "term": term,
                "pause_ts": pause_ts,
                "explanation": explanation,
                "status": status,
                "reason": reason,
                "nearest": nearest,
                "sim": round(sim, 3) if sim is not None else None,
                "mentions": mentions,
            }
        )
    return plan


def reset_sessions(conn, dry_run: bool = True) -> dict[str, int]:
    """Before a recording: drop all events and every "I already know this" click; keep notes and cached verdicts.

    Clicks are the only rows stored as (source video, status known); covered notes verdicts are source notes.
    """
    counts = {
        "events": conn.execute("SELECT count(*) FROM events").fetchone()[0],
        "known_clicks": conn.execute(
            "SELECT count(*) FROM learner_terms WHERE source = 'video' AND status = 'known'"
        ).fetchone()[0],
    }
    if not dry_run:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM learner_terms WHERE source = 'video' AND status = 'known'")
    return counts
