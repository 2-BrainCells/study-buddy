# User study: does Study Buddy pause on the right terms?

Written before any data is collected (25 Oct 2026). Changes made after the first real session are listed at
the bottom, with the date and the reason, so it's clear what was planned and what was adjusted.

## 1. Question

**Main (A):** Does Study Buddy pause on terms this learner doesn't know, and skip the ones they do?
**Supporting (C):** How does the experience feel: are the pauses helpful or disruptive, and would people use it?

Quiz scores are reported descriptively only. Without a baseline, a right answer can't show that someone
*learned* the term, so this study makes no learning claims.

## 2. Metrics

Every metric is computed from data the app already stores (`events`, `learner_terms`) or from the survey,
so anyone with the data can recompute it. The exact SQL is in `docs/STUDY_ANALYSIS.sql`.

| Metric | Definition | Source |
|---|---|---|
| Pauses | distinct terms with a `pause` event for this learner (study mode). `glance` events are counted separately | `events` |
| **False-pause rate** | paused terms the learner also marked "I already know this" (`known` event) ÷ pauses | `events` |
| Pointless stops (secondary, descriptive) | stops where **every** paused term was marked "I already know this". One stop can explain several terms (they share a `pause_ts`), so a stop with one known and one new term still helped | `events`, `terms` |
| Skipped terms | video terms already in the learner's profile **before** the session (`learner_terms.source` = `questionnaire` or `notes`, status `known`). Rows with `source = 'video'` are excluded: they are "I already know this" clicks and the novelty check's cached "not in notes" verdicts | `learner_terms` |
| **False skips** | skipped terms the learner says they didn't know (survey Q5), plus wrong quiz answers on skipped terms (the quiz only includes skipped terms when the learner has fewer than 5 new ones) | survey + `events` |
| Saved for the end | new terms beyond the 5-pause cap (shown after the video, not paused) | reconstructed from the plan |
| Quiz accuracy | correct ÷ answered, descriptive only | `events` |
| Completion | signed up → at least one pause → at least one quiz answer | `learners`, `events` |
| Experience | survey ratings (Q3, Q4, Q7) and free-text answers | survey |

Each metric is reported per learner and overall, split by whether the learner added notes, with n always shown.
Rates are given as counts too ("4 of 23"), never as a bare percentage.

## 3. Hypotheses

Written by Abhinav on 27 Oct 2026, before the pilot and before any participant data.

- **H1.** About **4 in 10 pauses** will be on terms the learner already knew (false-pause rate ≈ 40%).
  *Reasoning:* the system tells clearly different terms apart, but not very similar ones (e.g.
  "gradient descent" and "gradient"), so it will pause on terms the learner effectively already knows.
- **H1b (mechanism).** Most false pauses will be on a term that has a near-twin in this clip's term list
  (see the check below), e.g. a pause on "gradient descent algorithm" for a learner who knows "gradient descent".
  If this holds, the fix is to merge near-twins; if not, false pauses have another cause.
- **H2.** Learners who add notes will get **more** false pauses than learners who don't (direction only).
  *Reasoning:* the system may pause on two very similar terms.
  *Caveat:* people who add notes probably know more ML, so they have more known terms that could be
  paused on. A difference could come from prior knowledge, not the notes. Where possible, compare
  learners at the same familiarity level (survey Q2). With about 3 people per group, H2 is reported as an
  observation, not a conclusion.
- **H3.** About **2 false skips per learner**: skipped terms the learner didn't actually know.
- **It fails if** more than **4 in 10 pauses** are on terms the learner already knew. *Why 4:* that many
  pointless pauses is tolerable in one session, but not something I'd keep coming back to.
- **Precision:** with about 30 pauses in total, a measured rate is uncertain by roughly ±18 points
  (1.96 × √(0.4 × 0.6 / 30)), more since pauses from one learner aren't independent. A result within about
  15 points of 40% counts as **inconclusive**. Results are reported as counts with a range, never as a bare
  percentage.

*Checked 27 Oct against the demo clip's 21 terms (live site):* "gradient descent" and "gradient descent
algorithm" are both separate terms, and other near-pairs exist (local minimum / local optimum / global
minimum, initial point / initialization, steepest descent / gradient descent). The profile matches terms
by exact text (`classify` in `backend/app/learner.py`), so knowing one of a pair doesn't mark the other as
known.

## 4. Participants

- **Target:** 6–10 people, recruited from classmates and friends.
- **A deliberate mix of prior knowledge**, because the clip is CS229 gradient descent and people who
  know ML well may get no pauses at all:
  - about a third new to ML
  - about a third who know some
  - about a third who know it well
- Recorded per person: the onboarding questionnaire (already in the app), whether they added notes, and
  observed or on their own.
- **Known bias:** not a random sample, and participants know the author, so ratings will lean positive.
  Concrete complaints and observed behaviour count for more than scores.

## 5. Protocol

**Before anyone:** a pilot. First the author goes through the full flow, then one friend. Fix what breaks,
and log the changes at the bottom of this file.

**Spread sessions over 2–3 days**, so problems found early can be fixed. Notes indexing and the novelty
check use the model (DeepInfra: about $0.0007 per learner, $2/month limit). The novelty check takes about
40–100 s after notes are added.

### Observed sessions (2–3 people, about 30 min, in person or screen-share)

1. Consent (section 6), out loud; they say yes.
2. They sign up on the live site with the invite code, using a nickname if they like, and answer the questionnaire.
3. **Optional:** they paste their own study notes on the topic, then wait about 4 minutes before starting, so the plan includes the notes check.
4. They watch in **Study** mode and think aloud. *The author stays quiet and takes notes:* where they
   hesitate, what they say at each pause, whether they click "I already know this", anything confusing.
   No help unless they're stuck for more than a minute (and if so, note it).
5. Quiz, then the survey (section 7).
6. Two questions from the author: "Was there a pause you didn't need?" and "Was there a term you wish it had stopped for?"

### On their own (the rest)

The same steps, sent as one message: the link, the invite code, the consent text, "use one browser on one
device from sign-up to survey (your learner is saved in that browser only)", "use Study mode",
"if you add notes, wait about 4 minutes before pressing play", and "the survey link is on the quiz page".

## 6. Consent (shown before sign-up; observed participants hear it out loud)

> Study Buddy is a student project. If you take part:
> - The app records which terms it paused on, your "I already know this" clicks, and your quiz answers.
>   You'll also fill in a short survey.
> - **If you paste notes, they are sent to DeepInfra, a model-hosting service, to find the terms they
>   cover. DeepInfra says it doesn't store them.** Paste only study notes, never anything personal.
> - Use a nickname if you like. Your name is never shown publicly.
> - Results are reported anonymously and in aggregate. Quotes are used only if you say yes in the survey.
> - You can stop at any time, and ask for your data to be deleted. Deleting your learner removes your
>   notes, profile and events.

## 7. Survey (Tally or Google Forms, linked from the quiz page)

1. Your learner number (shown on the quiz page).
2. Before today, how familiar were you with gradient descent? (1 = never heard of it … 5 = could teach it)
3. "The video paused on terms I didn't know." (1 = strongly disagree … 5 = strongly agree)
4. The number of pauses felt: too few / about right / too many.
5. The quiz page lists "terms skipped because you seem to know them". **Were any of them actually unfamiliar? Which ones?**
6. Did a pause ever come at a bad moment, or feel unnecessary? Which one, and why?
7. "I'd use this for my own lectures." (1–5), and why?
8. Anything confusing or broken?
9. May I quote your answers anonymously? (yes / no)

## 8. Limitations (written in advance)

- One 16-minute clip on one topic; the results may not hold for other lectures.
- 6–10 participants, not randomly chosen, who know the author: there's no statistical significance, and
  every number is a description of this group.
- "I already know this" is a proxy for "didn't need this pause". Some people may click it to dismiss a
  card, and some may not bother to click.
- False skips rely mostly on self-report.
- No control condition (for example, pausing on every term), so the study can't say Study Buddy beats an
  alternative, only how well it matched these learners.
- The "saved for the end" cap (5 pauses) means some new terms are never paused, by design.

## 9. Deleting a participant's data

On Neon: `DELETE FROM learners WHERE id = <learner number>;`. Notes, profile terms and events are removed by
`ON DELETE CASCADE`. Cost rows stay, without the learner (`ON DELETE SET NULL`). Note the deletion in the
change log below, without the name.

## Change log

| Date | Change | Why |
|---|---|---|
| 25 Oct 2026 | First version | Written before the pilot |
| 27 Oct 2026 | Hypotheses (section 3) written by Abhinav | Before the pilot and any participant data |
| 27 Oct 2026 | The quiz page now lists the skipped terms, shows the learner number and links the survey (https://forms.gle/F1DNbTogv5jdKUhS9); Q5 reworded to point there | The skipped list was only on the player page, which participants have left by the time they answer Q5, so false skips would have relied on memory. No participant data existed yet |
| 28 Oct 2026 | Models moved from AMD Token Factory to DeepInfra (same models); the consent text now names DeepInfra, and section 5's budget and timing are updated | The Token Factory key stopped working after the hackathon (401). The novelty eval on DeepInfra matched the earlier result exactly (DECISIONS #85). No participant data existed yet |
| 29 Oct 2026 | Pilot part 1 (the author) done on the live site; every metric could be computed. Added the secondary metric "pointless stops" (H1 stays per term) and `docs/STUDY_ANALYSIS.sql`; corrected the description of `source = 'video'` rows | The pilot showed that one stop can explain two terms, so a per-term false pause isn't always a pointless interruption, which is what the "fails if" reasoning is about. Written before any participant data; the pilot session is not study data |
| 29 Oct 2026 | Pilot learners deleted from Neon (section 9): the author's pilot session, plus 4 extra sign-ups by the author with no activity (0 events, 0 notes) | So none of them are counted as participants by `STUDY_ANALYSIS.sql` |
| 29 Oct 2026 | Instructions now say to use one browser on one device throughout | The author's extra sign-ups came from using several browsers; a participant doing that would be split across learners |
