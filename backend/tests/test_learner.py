"""Tests for the novelty rules and text helpers (no models, no database)."""

from types import SimpleNamespace

import httpx
import openai
from app.learner import (
    OFFLINE,
    CoverageOut,
    Verdict,
    check_coverage,
    chunk_text,
    classify,
    safe_coverage,
)
from pipeline.embed import to_vector


class FakeTF:
    """Stands in for TokenFactory: returns canned replies in order and records each call's stage."""

    def __init__(self, *replies, novelty_model=None):
        self.replies = list(replies)
        self.calls: list[str] = []
        self.models: list[str | None] = []
        self.settings = SimpleNamespace(novelty_model=novelty_model)

    def chat_json(self, stage, out_model, messages, **kwargs):
        self.calls.append(stage)
        self.models.append(kwargs.get("model"))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def verdict(term: str, covered: bool) -> Verdict:
    return Verdict(
        term=term, covered=covered, evidence="alpha = 0.1" if covered else ""
    )


def test_profile_wins_over_verdict():
    v = {"gradient descent": verdict("gradient descent", True)}
    assert classify("Gradient Descent", {"gradient descent": ("new", "video")}, v) == ("new", "not in notes")


def test_known_reason_says_where_the_learner_knows_it_from():
    profile = {"chain rule": ("known", "questionnaire"), "mse": ("known", "notes"), "contours": ("known", "video")}
    assert classify("Chain rule", profile, {})[1] == "from your questionnaire"
    assert classify("MSE", profile, {})[1] == "in your notes"
    assert classify("contours", profile, {})[1] == "you marked it known"


def test_verdict_decides_terms_not_in_profile():
    v = {
        "learning rate": verdict("learning rate", True),
        "contours": verdict("contours", False),
    }
    assert classify("Learning rate", {}, v) == ("known", "notes: alpha = 0.1")
    assert classify("contours", {}, v) == ("new", "not in notes")


def test_term_without_verdict_is_new_and_says_why():
    assert classify("colon equals", {}, {}) == ("new", "not checked against notes")


def test_check_coverage_is_one_call_keyed_by_lowercase_term():
    tf = FakeTF(CoverageOut(verdicts=[verdict("Learning Rate", True)]))
    out = check_coverage(tf, "alpha = 0.1", ["Learning Rate"], learner_id=1, video_id=1)
    assert list(out) == ["learning rate"] and tf.calls == ["novelty"]


def test_no_notes_means_no_llm_call():
    tf = FakeTF()
    assert check_coverage(tf, "  ", ["learning rate"], learner_id=1, video_id=1) == {}
    assert tf.calls == []


def test_chunk_text_keeps_paragraphs_whole():
    paras = ["one two three", "four five", "six"]
    chunks = chunk_text("\n\n".join(paras), size=4)
    assert chunks == ["one two three\n\nfour five", "six"]


def test_to_vector_is_pgvector_text():
    assert to_vector([0.1, 0.2]) == "[0.100000,0.200000]"


def test_model_down_means_pause_on_every_open_term_and_say_why():
    down = openai.APIConnectionError(request=httpx.Request("POST", "https://tf.test/v1/chat/completions"))
    tf = FakeTF(down)
    assert safe_coverage(tf, "alpha = 0.1", ["learning rate"], learner_id=1, video_id=1) == ({}, False)
    assert safe_coverage(None, "alpha = 0.1", ["learning rate"], learner_id=1, video_id=1) == ({}, False)
    assert classify("learning rate", {}, {}, checked=False) == ("new", OFFLINE)


def test_novelty_uses_its_own_model_and_falls_back_to_the_default():
    down = openai.APIConnectionError(request=httpx.Request("POST", "https://tf.test/v1/chat/completions"))
    tf = FakeTF(down, CoverageOut(verdicts=[verdict("learning rate", True)]), novelty_model="Gemma-4-31B-IT")
    verdicts, checked = safe_coverage(tf, "alpha = 0.1", ["learning rate"], learner_id=1, video_id=1)
    assert checked and list(verdicts) == ["learning rate"]
    assert tf.models == ["Gemma-4-31B-IT", None]  # Gemma first, then LLM_MODEL

