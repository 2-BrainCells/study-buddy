"""Export the demo clip's quiz questions and terms to CSVs for hand labelling (docs/EVAL.md).

Usage, from backend/: python eval_export.py [video_id]   (DATABASE_URL must point at the database to label)
Writes ../data/eval/quiz.csv and terms.csv (data/ is never committed). Refuses to overwrite, so labels
already typed into a CSV can't be lost. Files are UTF-8 with a BOM, so Excel shows θ and ∇ correctly.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg

OUT = Path("../data/eval")

# answer last, so it can be hidden while labelling; the label columns stay empty for the labeller
QUIZ_SQL = """
SELECT q.id, t.term, q.question,
       q.options->>0, q.options->>1, q.options->>2, q.options->>3,
       '', '', '', '', '', '', '', q.answer
FROM quiz_questions q JOIN terms t ON t.id = q.term_id
WHERE q.video_id = %s
ORDER BY q.id
"""
QUIZ_HEADER = [
    "id",
    "term",
    "question",
    "opt0",
    "opt1",
    "opt2",
    "opt3",
    "my_answer",
    "c1",
    "c2",
    "c3",
    "c4",
    "c5",
    "note",
    "answer",
]

# transcript around the pause: from 15 s before the first mention, split at the pause. A segment that
# spans pause_ts lands in `before`, so the exact cut can be up to one segment off; check those in the player
TERMS_SQL = """
SELECT t.id, t.term, round(t.first_ts::numeric, 1), round(t.pause_ts::numeric, 1),
       (SELECT string_agg(s.text, ' ' ORDER BY s.start_s) FROM segments s
        WHERE s.video_id = t.video_id AND s.end_s > t.first_ts - 15 AND s.start_s < t.pause_ts),
       (SELECT string_agg(s.text, ' ' ORDER BY s.start_s) FROM segments s
        WHERE s.video_id = t.video_id AND s.start_s >= t.pause_ts AND s.start_s < t.pause_ts + 20),
       '', '', '', ''
FROM terms t
WHERE t.video_id = %s
ORDER BY t.pause_ts
"""
TERMS_HEADER = [
    "id",
    "term",
    "first_ts",
    "pause_ts",
    "before_pause",
    "after_pause_20s",
    "extraction",
    "placement",
    "duplicate_of",
    "note",
]


def export(conn, sql: str, header: list[str], video_id: int, path: Path) -> int:
    """Write one query's rows to a new CSV and return the row count."""
    rows = conn.execute(sql, (video_id,)).fetchall()
    with path.open(
        "x", newline="", encoding="utf-8-sig"
    ) as f:  # "x": fail if it exists
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def main(video_id: int) -> None:
    """Export both CSVs for one video."""
    OUT.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for name, sql, header in [
            ("quiz", QUIZ_SQL, QUIZ_HEADER),
            ("terms", TERMS_SQL, TERMS_HEADER),
        ]:
            n = export(conn, sql, header, video_id, OUT / f"{name}.csv")
            print(f"{OUT / name}.csv: {n} rows")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
