"""Find terms with the LLM, then place each pause at the end of the sentence that introduces it."""

import random

import pydantic
from pydantic import BaseModel, ConfigDict, Field

from pipeline.llm import EmptyReplyError, TokenFactory
from pipeline.transcribe import Word

NEAR_DUP = 0.90  # BGE-M3 cosine; on the lecture 2 clip only true duplicates scored above it
CHUNK_WORDS = 600  # ~4 min of speech, ~1k input tokens
SENTENCE_END = (".", "?", "!")


class QuizOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    answer: int = Field(ge=0, le=3)  # index into options


class TermOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str
    explanation: str
    quiz: list[QuizOut] = Field(min_length=2, max_length=2)


class ChunkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[TermOut]


def split_sentences(words: list[Word]) -> list[list[Word]]:
    """Group words into sentences using Whisper's punctuation."""
    sentences: list[list[Word]] = []
    current: list[Word] = []
    for w in words:
        current.append(w)
        if w.text.endswith(SENTENCE_END):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def chunk(words: list[Word], size: int = CHUNK_WORDS) -> list[list[Word]]:
    """Pack whole sentences into chunks of about `size` words (one LLM call each)."""
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for sentence in split_sentences(words):
        current += sentence
        if len(current) >= size:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _clean(token: str) -> str:
    return token.lower().strip(".,?!;:\"'()")


def place(term: str, words: list[Word]) -> tuple[float, float] | None:
    """Return (first_ts, pause_ts) for the first time `term` is said, or None if it never is."""
    target = [_clean(t) for t in term.split()]
    tokens = [_clean(w.text) for w in words]
    n = len(target)
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] == target:
            end = next(
                (w for w in words[i + n - 1 :] if w.text.endswith(SENTENCE_END)),
                words[-1],
            )
            return words[i].start, end.end
    return None


PROMPT = """You help a beginner follow a machine learning lecture.
From the transcript excerpt below, pick up to 8 technical terms a newcomer may not know.
Copy each term EXACTLY as it appears in the excerpt.
For each term: a 2-3 sentence plain-English explanation, and 2 multiple-choice questions
with 4 options each; "answer" is the index (0-3) of the correct option.
Pick specific technical terms only (like "gradient descent"), not everyday words (like "questions" or "part").
Do not list a term that is part of a longer term you already listed.

Excerpt:
"""


def _ask_with_repair(tf: TokenFactory, prompt: str, video_id: int) -> ChunkOut:
    """Ask for one chunk's terms; if the reply breaks the schema, ask once more with the validation error.

    JSON mode guarantees valid JSON, not the right shape (1 of 5 chunks failed on the lecture 2 clip).
    """
    try:
        return tf.chat_json(
            "terms", ChunkOut, [{"role": "user", "content": prompt}], video_id=video_id
        )
    except pydantic.ValidationError as e:
        repair = f"{prompt}\n\nYour previous reply failed validation:\n{str(e)[:1000]}\nFollow the schema exactly."
        return tf.chat_json(
            "terms_repair",
            ChunkOut,
            [{"role": "user", "content": repair}],
            video_id=video_id,
        )


def extract_terms(
    tf: TokenFactory, chunks: list[list[Word]], video_id: int
) -> tuple[list[TermOut], int]:
    """One LLM call per chunk. Returns terms (deduped, first mention wins) and the count of failed chunks."""
    found: dict[str, TermOut] = {}
    failed = 0
    for words in chunks:
        text = " ".join(w.text for w in words)
        try:
            out = _ask_with_repair(tf, PROMPT + text, video_id)
        except (pydantic.ValidationError, EmptyReplyError) as e:
            # counted and reported in the summary, not hidden; endpoint errors still stop the run
            print(f"chunk failed validation: {type(e).__name__}: {str(e)[:200]}")
            failed += 1
            continue
        for t in out.terms:
            found.setdefault(t.term.lower(), t)
    return list(found.values()), failed


def shuffle_options(q: QuizOut, rng: random.Random) -> tuple[list[str], int]:
    """Shuffle options so the right answer isn't always where the LLM put it."""
    order = list(range(len(q.options)))
    rng.shuffle(order)
    return [q.options[i] for i in order], order.index(q.answer)

def drop_nested(
    placed: list[tuple[TermOut, tuple[float, float]]],
) -> list[tuple[TermOut, tuple[float, float]]]:
    """Drop a term that is part of a longer term pausing at the same moment ("gradient" in "gradient descent")."""
    return [
        (t, p)
        for t, p in placed
        if not any(
            o is not t and op[1] == p[1] and t.term.lower() in o.term.lower() and len(o.term) > len(t.term)
            for o, op in placed
        )
    ]


def drop_near_duplicates(
    kept: list[tuple[TermOut, tuple[float, float]]],
    vectors: list[list[float]],
    threshold: float = NEAR_DUP,
) -> tuple[list[tuple[TermOut, tuple[float, float]]], list[list[float]]]:
    """Drop a term whose (normalised) embedding is within `threshold` cosine of one introduced earlier.

    "local optima" after "local optimum": the earliest wording wins, since that is where the idea is introduced.
    """
    # ponytail: O(n^2) dot products in pure Python; fine for ~30 terms per clip, use numpy if lectures yield hundreds
    order = sorted(range(len(kept)), key=lambda i: kept[i][1][0])
    keep: list[int] = []
    for i in order:
        if all(sum(a * b for a, b in zip(vectors[i], vectors[j])) < threshold for j in keep):
            keep.append(i)
    keep.sort()
    return [kept[i] for i in keep], [vectors[i] for i in keep]
