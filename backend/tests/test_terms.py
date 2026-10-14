"""Tests for chunking, term placement, extraction and quiz shuffling (no real models)."""

import random

import pydantic
import pytest
from pipeline.terms import (
    ChunkOut,
    QuizOut,
    TermOut,
    chunk,
    extract_terms,
    place,
    shuffle_options,
)
from pipeline.transcribe import Word


def words(text: str) -> list[Word]:
    return [Word(i * 0.5, i * 0.5 + 0.4, t) for i, t in enumerate(text.split())]


W = words("We use gradient descent here. It converges slowly. Gradient descent again!")
#          0  1   2        3       4     5  6         7       8        9       10
QUIZ = QuizOut(question="q", options=["a", "b", "c", "d"], answer=0)


def term(name: str) -> TermOut:
    return TermOut(term=name, explanation="x", quiz=[QUIZ, QUIZ])


def validation_error() -> pydantic.ValidationError:
    try:
        ChunkOut.model_validate_json("{}")
    except pydantic.ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


class FakeTF:
    """Stands in for TokenFactory: returns (or raises) canned replies in order and records each call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []  # (stage, prompt)

    def chat_json(self, stage, out_model, messages, **kwargs):
        self.calls.append((stage, messages[-1]["content"]))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_place_pauses_at_end_of_sentence():
    assert place("gradient descent", W) == (W[2].start, W[4].end)


def test_place_ignores_case_and_punctuation():
    assert place("Converges", W) == (W[6].start, W[7].end)


def test_place_returns_none_when_term_never_said():
    assert place("logistic regression", W) is None


def test_chunks_keep_sentences_whole_and_lose_no_words():
    chunks = chunk(W, size=3)
    assert all(c[-1].text.endswith((".", "!", "?")) for c in chunks)
    assert sum(len(c) for c in chunks) == len(W)


def test_extract_dedupes_and_counts_chunks_that_fail_twice():
    tf = FakeTF(
        ChunkOut(terms=[term("Gradient descent")]),
        validation_error(),  # chunk 2: first try
        validation_error(),  # chunk 2: repair also fails
        ChunkOut(terms=[term("gradient descent"), term("cost function")]),
    )
    terms, failed = extract_terms(tf, [W, W, W], video_id=1)
    assert [t.term for t in terms] == ["Gradient descent", "cost function"]
    assert failed == 1


def test_invalid_reply_is_repaired_with_the_error_in_the_prompt():
    tf = FakeTF(validation_error(), ChunkOut(terms=[term("cost function")]))
    terms, failed = extract_terms(tf, [W], video_id=1)
    assert [t.term for t in terms] == ["cost function"] and failed == 0
    (first_stage, _), (repair_stage, repair_prompt) = tf.calls
    assert (first_stage, repair_stage) == ("terms", "terms_repair")
    assert "failed validation" in repair_prompt and "terms" in repair_prompt


def test_valid_reply_makes_one_call():
    tf = FakeTF(ChunkOut(terms=[term("cost function")]))
    extract_terms(tf, [W], video_id=1)
    assert [stage for stage, _ in tf.calls] == ["terms"]


@pytest.mark.parametrize("seed", range(5))
def test_shuffle_keeps_the_right_answer(seed):
    q = QuizOut(question="q", options=["right", "w1", "w2", "w3"], answer=0)
    options, answer = shuffle_options(q, random.Random(seed))
    assert options[answer] == "right" and sorted(options) == sorted(q.options)
