"""PostToolUse: ruff-format edited .py files and push leftover lint errors back to Claude."""
import json
import subprocess
import sys


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        return 0

    ruff = [sys.executable, "-m", "ruff"]
    subprocess.run(ruff + ["format", path], capture_output=True)
    check = subprocess.run(ruff + ["check", "--fix", path],
                           capture_output=True, text=True, encoding="utf-8")

    if check.returncode != 0:
        print(json.dumps({
            "decision": "block",
            "reason": f"ruff found issues it could not auto-fix in {path}:\n"
                      f"{check.stdout[-3000:]}\nFix them before continuing.",
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())