# Eval: quiz questions and paused terms

Written before any labels (30 Oct 2026). Changes after labelling starts go in the change log at the bottom.

## 1. What is measured
- Quiz: all 42 questions of the demo clip (video 4).
- Terms: all 21 terms of the demo clip, on extraction (a) and placement (b).
- Not here: per-learner novelty (c); the user study measures it.

## 2. Quiz rubric (yes/no per question)
| # | Criterion | Pass when | Fail example (made up) |
|---|---|---|---|
| C1 | Correct | The marked answer is right, by the lecture and standard ML usage | "What does the learning rate control?" marked answer: "the number of training examples" |
| C2 | Unambiguous | Exactly one option can be defended as right by someone who knows the term well. A hard question can still pass | "How does gradient descent update θ?" with both "θ := θ − α∇J(θ)" and "it moves θ against the gradient" as separate options |
| C3 | Tests the term | Answering needs knowing what the term means or does; it can't be answered from the term's name alone, or by matching the lecture's exact wording | "In gradient descent, what do we descend along?" → "the gradient" (the name gives it away) |
| C4 | Plausible distractors | Every wrong option is something a learner who half-knows the term might pick, and the right option doesn't stand out by length or detail | "What is the learning rate?" options: "the step size", "a type of regularisation", "a GPU setting", "a fish" |
| C5 | Answerable from the clip | Everything needed is taught in the clip, or is school-level maths (e.g. what a derivative is) | A question about Adam's β₂ when the clip covers only plain gradient descent |

Usable = passes C1, C2 and C3. C4 and C5 are reported separately.
Procedure: answer each question with the key hidden, then reveal it and mark C1–C5. Note the reason for every fail.

## 3. Term labels
(a) Extraction, one of:
- real concept: a named idea, method or object from ML or maths that the clip uses and a learner could look up (e.g. "cost function")
- generic word: an everyday or too-broad word that doesn't deserve a card (e.g. "algorithm", "data")
- off-topic: a real concept, but only mentioned in passing; the clip neither explains it nor relies on it
Also note `duplicate_of = <other term>` when two terms are the same idea in different words (feeds H1b in STUDY.md).

(b) Placement, judged from the transcript around pause_ts, one of:
- good: the pause comes after the sentence where the term is first explained (not just named), and before the lecturer moves to the next idea
- early: the term is named, but the lecturer's own explanation comes after the pause (the card spoils it or duplicates it)
- late: the lecturer has already moved to another idea
- wrong spot: mid-sentence, or at a mention unrelated to the term

## 4. Consistency check
Re-label 10 questions and 5 terms at least 2 days later (on or after 2 Nov), without looking at the first labels.
The sample is fixed now, so I can't pick easy ones:
```sql
-- questions
SELECT id FROM quiz_questions WHERE video_id = 4 ORDER BY md5(id::text) LIMIT 10;
-- terms
SELECT id FROM terms WHERE video_id = 4 ORDER BY md5(id::text) LIMIT 5;
```

If a friend is available, they label the same 10 questions with this rubric only.
Report agreement per criterion as "k of 10". A criterion below 8 of 10 is unclear: rewrite it, re-label it, and log the change.

ORDER BY md5(id::text) gives a random-looking order that's identical every time you run it. You can't steer the sample, and anyone can reproduce it.

## 5. Expectations (before labelling)
- I expect about 30 of 42 questions to be usable (reasons below).
- Most likely failing criterion: C2 and C3, MiMo knows gradient descent well, so C1 should rarely fail; the 12 failures will mostly be C2/C3, because each question is written from one ~600-word chunk of transcript and may test its wording. Below 25 usable, the quiz needs fixing before the case study.

## Change log
| Date | Change | Why |