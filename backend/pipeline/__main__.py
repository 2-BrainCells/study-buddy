"""CLI: python -m pipeline <command>  (run from backend/)."""

import argparse
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


def main() -> None:
    load_dotenv()  # finds ../.env locally; does nothing in Docker, where env_file already set the vars
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-endpoint", help="verify key, models and one JSON call")
    p = sub.add_parser("process", help="run the per-video pipeline on one video")
    p.add_argument("video", type=Path)
    p.add_argument("--title", required=True)
    args = parser.parse_args()
    if args.command == "check-endpoint":
        sys.exit(check_endpoint())
    if args.command == "process":
        from pipeline.process import (
            process,
        )  # torch is slow to import; only load it for this command

        process(args.video, args.title)


if __name__ == "__main__":
    main()
