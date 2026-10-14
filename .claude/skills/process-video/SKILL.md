---
name: process-video
description: Run the per-video pipeline on one lecture and report stage costs
argument-hint: "[path to video, e.g. data/videos/cs229-lecture02.mp4]"
disable-model-invocation: true
---

Process the lecture video at $ARGUMENTS.

1. From backend/, run `python -m pipeline check-endpoint`, which reads the
   model settings from .env itself. If it fails, stop and tell me the
   endpoint is down.
2. From backend/, run `python -m pipeline process $ARGUMENTS --title "<title>"`.
   Video paths are relative to backend/, e.g. `../data/videos/...`; ask me
   for the title if I didn't give one.
3. When it finishes, query the stage_costs table for this video and show a
   table: stage (transcribe, terms, terms_repair, embed), requests, input
   tokens, output tokens, 429 retries, latency.
4. Report how many terms (each with a pause point) and quiz questions were
   cached (count rows in terms and quiz_questions), and the totals per
   lecture hour for the cost slide.
5. If a stage failed, show the last 30 lines of its log and suggest a fix.
   Do not re-run the whole pipeline without asking.