"""eval_score: invalid labels are reported, never scored; valid ones are counted the way docs/EVAL.md defines."""

from eval_score import quiz_problems, quiz_scores, term_problems


def quiz_row(**overrides) -> dict:
    """A valid, fully passing quiz row; overrides change single cells."""
    row = {"id": "1", "my_answer": "2", "answer": "2", "note": ""} | {
        c: "1" for c in ("c1", "c2", "c3", "c4", "c5")
    }
    return row | overrides


def test_valid_rows_have_no_problems():
    assert (
        quiz_problems([quiz_row(), quiz_row(c4="0", note="option 3 is longest")]) == []
    )


def test_blank_or_unknown_labels_are_problems():
    assert quiz_problems([quiz_row(c1="")]) == ["quiz 1: empty or invalid c1"]
    assert quiz_problems([quiz_row(my_answer="4")]) == [
        "quiz 1: empty or invalid my_answer"
    ]


def test_fail_and_mismatch_need_a_note():
    assert quiz_problems([quiz_row(c2="0")]) == ["quiz 1: fail without a note"]
    assert quiz_problems([quiz_row(my_answer="0")]) == [
        "quiz 1: blind answer differs from the key without a note"
    ]


def test_usable_needs_c1_to_c3_only():
    rows = [quiz_row(), quiz_row(c4="0", c5="0", note="x"), quiz_row(c3="0", note="x")]
    assert "usable (C1+C2+C3): 2 of 3" in quiz_scores(rows)


def test_terms_need_rubric_values():
    good = {"id": "7", "extraction": "real concept", "placement": "good"}
    assert term_problems([good]) == []
    assert len(term_problems([good | {"extraction": "NA", "placement": ""}])) == 2
