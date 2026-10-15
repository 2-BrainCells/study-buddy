"""Tests for the novelty rules and text helpers (no models, no database)."""

from app.learner import CoverageOut, Verdict, check_coverage, chunk_text, classify
from pipeline.embed import to_vector


class FakeTF:
    """Stands in for TokenFactory: returns canned replies in order and records each call's stage."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[str] = []

    def chat_json(self, stage, out_model, messages, **kwargs):
        self.calls.append(stage)
        return self.replies.pop(0)


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
