"""Score the hand labels in data/eval (docs/EVAL.md). Usage, from backend/: python eval_score.py <quiz.csv> <terms.csv>

Validates first: an empty or unknown label, a fail without a note, or a blind answer that differs from the key
without a note stops it before any score is printed, so a gap can't pass silently as a pass or a fail.
"""

import csv
import sys
from collections import Counter

CRITERIA = ["c1", "c2", "c3", "c4", "c5"]
USABLE = CRITERIA[:3]  # correct, unambiguous, tests the term
EXTRACTION = {"real concept", "generic word", "off-topic"}
PLACEMENT = {"good", "early", "late", "wrong spot"}


def read(path: str) -> list[dict]:
    """Rows of a labels CSV, values stripped."""
    # utf-8-sig: the export writes a BOM, which plain utf-8 would leave stuck to the first column name
    with open(path, newline="", encoding="utf-8-sig") as file:
        return [
            {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            for row in csv.DictReader(file)
        ]


def quiz_problems(rows: list[dict]) -> list[str]:
    """One message per invalid quiz row, e.g. '141: fail without a note'."""
    problems = []
    for r in rows:
        bad = [c for c in CRITERIA if r.get(c) not in ("0", "1")]
        if r.get("my_answer") not in ("0", "1", "2", "3"):
            bad.append("my_answer")
        if bad:
            problems.append(f"quiz {r['id']}: empty or invalid {', '.join(bad)}")
            continue
        if not r.get("note"):
            if "0" in (r[c] for c in CRITERIA):
                problems.append(f"quiz {r['id']}: fail without a note")
            if r["my_answer"] != r["answer"]:
                problems.append(
                    f"quiz {r['id']}: blind answer differs from the key without a note"
                )
    return problems


def term_problems(rows: list[dict]) -> list[str]:
    """One message per invalid term row: extraction and placement must be rubric values."""
    problems = []
    for r in rows:
        if r.get("extraction") not in EXTRACTION:
            problems.append(
                f"term {r['id']}: extraction {r.get('extraction')!r} is not one of {sorted(EXTRACTION)}"
            )
        if r.get("placement") not in PLACEMENT:
            problems.append(
                f"term {r['id']}: placement {r.get('placement')!r} is not one of {sorted(PLACEMENT)}"
            )
    return problems


def quiz_scores(rows: list[dict]) -> list[str]:
    """Pass counts per criterion, the usable count and the blind-answer match, as report lines."""
    n = len(rows)
    lines = [
        f"{c.upper()}: {sum(r[c] == '1' for r in rows)} of {n} pass" for c in CRITERIA
    ]
    lines.append(
        f"usable (C1+C2+C3): {sum(all(r[c] == '1' for c in USABLE) for r in rows)} of {n}"
    )
    lines.append(
        f"blind answer matched the key: {sum(r['my_answer'] == r['answer'] for r in rows)} of {n}"
    )
    return lines


def term_scores(rows: list[dict]) -> list[str]:
    """Counts per extraction and placement label, and the duplicate pairs, as report lines."""
    n = len(rows)
    lines = []
    for column in ("extraction", "placement"):
        counts = Counter(r[column] for r in rows)
        lines.append(
            f"{column}: "
            + ", ".join(f"{label} {k} of {n}" for label, k in counts.most_common())
        )
    lines += [
        f"duplicate: {r['term']} -> {r['duplicate_of']}"
        for r in rows
        if r.get("duplicate_of")
    ]
    return lines


def main(quiz_path: str, terms_path: str) -> None:
    """Validate both label files, then print the scores; exit 1 without scores if any label is invalid."""
    quiz, terms = read(quiz_path), read(terms_path)
    problems = quiz_problems(quiz) + term_problems(terms)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(
        "\n".join(["== quiz", *quiz_scores(quiz), "", "== terms", *term_scores(terms)])
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
