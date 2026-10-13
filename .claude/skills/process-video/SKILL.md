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
2. From backend/, run `python -m pipeline process $ARGUMENTS`.
3. When it finishes, query the stage_costs table for this video and show a
   table: stage, requests, input tokens, output tokens, 429 retries,
   items processed.
4. Report how many terms, sentence ends and quiz questions were cached,
   and the totals per lecture hour for the cost slide.
5. If a stage failed, show the last 30 lines of its log and suggest a fix.
   Do not re-run the whole pipeline without asking.