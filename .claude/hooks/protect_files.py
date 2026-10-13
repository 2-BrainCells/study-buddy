"""PreToolUse: stop Claude editing secrets, lockfiles, git internals and demo data."""
import fnmatch
import json
import os
import sys

PROTECTED = [".env", ".env.*", "*.pem", "*.key", "package-lock.json",
             ".git/*", "data/videos/*", "data/notes/*", "*.mp4"]
ALLOWED = [".env.example"]


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "").replace("\\", "/")
    root = os.environ.get("CLAUDE_PROJECT_DIR", "").replace("\\", "/").rstrip("/")

    rel = path
    if root and path.lower().startswith(root.lower() + "/"):
        rel = path[len(root) + 1:]
    name = rel.rsplit("/", 1)[-1]
    if name in ALLOWED:
        return 0

    for pattern in PROTECTED:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern):
            print(f"Blocked: '{rel}' is protected ({pattern}). "
                  "Tell the user what change is needed instead.", file=sys.stderr)
            return 2  # block; stderr is shown to Claude
    return 0


if __name__ == "__main__":
    sys.exit(main())