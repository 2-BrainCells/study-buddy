"""PreToolUse: refuse destructive shell commands (Bash and PowerShell)."""
import json
import re
import sys

DANGEROUS = [
    (r"\brm\s+-\w*(rf|fr)", "recursive force delete (rm -rf)"),
    (r"Remove-Item\b.*-Recurse", "recursive delete (Remove-Item -Recurse)"),
    (r"\bgit\s+push\b.*(--force|\s-f\b)", "force push"),
    (r"\bgit\s+reset\s+--hard\b", "hard reset discards uncommitted work"),
    (r"\bdrop\s+(table|database)\b", "dropping a table or database"),
    (r"\bdocker\s+compose\s+down\b.*\s-v\b", "compose down -v deletes the Postgres volume"),
    (r"\bdocker\s+(system|volume)\s+prune\b", "prune deletes Docker volumes"),
]


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")

    for pattern, why in DANGEROUS:
        if re.search(pattern, command, re.IGNORECASE):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked by project policy: {why}. "
                        "Suggest a safer alternative or ask the user to run it."
                    ),
                }
            }))
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())