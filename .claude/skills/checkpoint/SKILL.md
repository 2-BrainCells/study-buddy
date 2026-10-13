---
name: checkpoint
description: Test, lint and commit the current work with a clear message
argument-hint: "[short summary of what changed]"
disable-model-invocation: true
---

Create a checkpoint commit for: $ARGUMENTS

1. Run `python -m ruff check backend` and fix anything it reports.
2. Run `python -m pytest -q` from backend/. If tests fail, stop and tell me
   which ones; do not commit.
3. Run `git status` and make sure nothing from data/, .env or node_modules/ is staged.
4. Commit with a message in the form "feat: <summary>" or "fix: <summary>".
5. Do not push. Tell me the commit hash and a one-line summary.