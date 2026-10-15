"""CLI: python -m pipeline <command>  (run from backend/)."""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from pipeline.llm import Settings, TokenFactory


class Ping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    word: str


def check_endpoint() -> int:
    """Verify key, model names and one strict-JSON call. Returns an exit code."""
    try:
        tf = TokenFactory(
            Settings.from_env(), cost_sink=print
        )  # a check doesn't belong in stage_costs
        print("models:", ", ".join(tf.check_models()))
        reply = tf.chat_json(
            "check",
            Ping,
            [{"role": "user", "content": 'Reply with ok=true and word="hello".'}],
        )
        if not reply.ok:
            raise RuntimeError(f"unexpected reply: {reply}")
    except Exception as e:  # noqa: BLE001  CLI boundary: report any failure, exit non-zero
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1
    print("PASS:", reply)
    return 0


def eval_novelty(learner_id: int, video_id: int, labels: Path) -> None:
    """Compare the novelty check's "known" against hand labels (CSV: term,in_notes with 1/0)."""
    import csv
    import os

    import psycopg
    from app.learner import video_plan

    from pipeline.llm import db_cost_sink

    raw = labels.read_bytes()
    # PowerShell 5.1's `>` writes UTF-16 with a BOM; editors usually write UTF-8
    text = raw.decode(
        "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    )
    truth = {
        r["term"].strip().lower(): r["in_notes"].strip()
        for r in csv.DictReader(text.splitlines())
    }
    tf = TokenFactory(Settings.from_env(), db_cost_sink(os.environ["DATABASE_URL"]))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        plan = video_plan(conn, tf, learner_id, video_id)

    tp = fp = fn = tn = skipped = 0
    for p in plan:
        label = truth.get(p["term"].lower(), "")
        print(
            f"{p['term'][:30]:30} sim={p['sim']!s:6} {p['status']:10} label={label or '-':2} ({p['reason']})"
        )
        if label not in ("0", "1"):
            skipped += 1
            continue
        known, actual = p["status"] == "known", label == "1"
        tp += known and actual
        fp += known and not actual
        fn += not known and actual
        tn += not known and not actual
    print(
        f"\nTP {tp}  FP {fp}  FN {fn}  TN {tn}  unlabelled {skipped}"
    )
    print(
        f"known: precision {tp / max(tp + fp, 1):.2f}, recall {tp / max(tp + fn, 1):.2f}"
    )
    print(
        "caveat: n is one learner on one clip; cached verdicts are reused, so delete source='video' rows to re-judge."
    )


def main() -> None:
    load_dotenv()  # finds ../.env locally; does nothing in Docker, where env_file already set the vars
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-endpoint", help="verify key, models and one JSON call")
    sub.add_parser("check-usage", help="show what quota data Token Factory reports (no tokens used)")
    p = sub.add_parser("process", help="run the per-video pipeline on one video")
    p.add_argument("video", type=Path)
    p.add_argument("--title", required=True)
    e = sub.add_parser(
        "eval-novelty", help="compare novelty statuses against hand labels"
    )
    e.add_argument("--learner", type=int, required=True)
    e.add_argument("--video", type=int, required=True)
    e.add_argument("--labels", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "eval-novelty":
        eval_novelty(args.learner, args.video, args.labels)
    if args.command == "check-usage":
        from pipeline.llm import rate_limits

        q = rate_limits(Settings.from_env())
        print("available:", q["available"])
        if q["available"]:
            print("x-ratelimit headers:", q["limits"] or "none")
            u = q["usage"] if isinstance(q["usage"], dict) else {}
            print("GET /usage keys:", sorted(u))
            for k in ("daily_cost_limit_usd", "daily_cost_used_usd", "daily_cost_remaining_usd", "daily_reset_at",
                      "rpm_limit", "window_hours"):
                print(f"  {k} = {u.get(k)}")
            for k in ("today", "last_24_hours", "by_model", "by_source"):  # shapes only; ids are not printed
                print(f"  {k}: {json.dumps(u.get(k))[:400]}")
        else:
            print("reason:", q["reason"])
    if args.command == "check-endpoint":
        sys.exit(check_endpoint())
    if args.command == "process":
        from pipeline.process import (
            process,
        )  # torch is slow to import; only load it for this command

        process(args.video, args.title)


if __name__ == "__main__":
    main()
