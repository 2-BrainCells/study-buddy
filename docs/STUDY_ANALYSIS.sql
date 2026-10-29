-- User study analysis (docs/STUDY.md, section 2). Run on Neon after the sessions; every participant is
-- analysed with exactly this SQL. Participants are real (invite-code) learners: token_hash IS NOT NULL.
-- Delete pilot learners first (STUDY.md section 9), or they are counted.
-- Assumes one clip per learner (the study uses one) and notes added before watching (the protocol).

-- 1. Per learner, per notes group, and overall (the rows with learner = NULL are the totals).
WITH participants AS (
    SELECT l.id, EXISTS (SELECT 1 FROM notes n WHERE n.learner_id = l.id) AS added_notes
    FROM learners l
    WHERE l.token_hash IS NOT NULL
),
clip AS (SELECT DISTINCT learner_id, video_id FROM events),
paused AS (SELECT DISTINCT learner_id, term_id FROM events WHERE type = 'pause'),
clicked AS (SELECT DISTINCT learner_id, term_id FROM events WHERE type = 'known'),
-- in the profile before the session; source 'video' rows are clicks and cached "not in notes" verdicts
skipped AS (
    SELECT lt.learner_id, t.id AS term_id
    FROM learner_terms lt
    JOIN clip c ON c.learner_id = lt.learner_id
    JOIN terms t ON t.video_id = c.video_id AND lower(t.term) = lt.term_text
    WHERE lt.status = 'known' AND lt.source IN ('questionnaire', 'notes')
),
per_learner AS (
    SELECT p.id AS learner,
           p.added_notes,
           (SELECT count(*) FROM terms t JOIN clip c ON c.video_id = t.video_id WHERE c.learner_id = p.id) AS clip_terms,
           (SELECT count(*) FROM paused x WHERE x.learner_id = p.id) AS paused,
           (SELECT count(*) FROM paused x JOIN clicked k USING (learner_id, term_id) WHERE x.learner_id = p.id) AS false_pauses,
           (SELECT count(*) FROM skipped s WHERE s.learner_id = p.id) AS skipped,
           (SELECT count(*) FROM events e JOIN skipped s ON s.learner_id = e.learner_id AND s.term_id = e.term_id
            WHERE e.learner_id = p.id AND e.type = 'quiz_answer' AND NOT e.correct) AS wrong_quiz_on_skipped,
           (SELECT count(*) FROM events e WHERE e.learner_id = p.id AND e.type = 'quiz_answer' AND e.correct) AS quiz_right,
           (SELECT count(*) FROM events e WHERE e.learner_id = p.id AND e.type = 'quiz_answer') AS quiz_answered
    FROM participants p
)
SELECT CASE WHEN GROUPING(learner) = 0 THEN learner::text
            WHEN GROUPING(added_notes) = 0 THEN CASE WHEN added_notes THEN 'notes group' ELSE 'no-notes group' END
            ELSE 'all' END AS row,
       count(*) AS learners,
       sum(paused) AS paused,
       sum(false_pauses) AS false_pauses,
       sum(skipped) AS skipped,
       sum(clip_terms - skipped - paused) AS saved_for_end,  -- new terms beyond the pause cap
       sum(wrong_quiz_on_skipped) AS wrong_quiz_on_skipped,  -- false skips from the quiz; add survey Q5 by hand
       sum(quiz_right) AS quiz_right,
       sum(quiz_answered) AS quiz_answered,
       count(*) FILTER (WHERE paused > 0) AS reached_a_pause,  -- completion: signed up -> paused -> quiz
       count(*) FILTER (WHERE quiz_answered > 0) AS answered_quiz
FROM per_learner
GROUP BY GROUPING SETS ((learner, added_notes), (added_notes), ())
ORDER BY GROUPING(added_notes), added_notes, GROUPING(learner), learner;

-- 2. Pointless stops (secondary metric, added 29 Oct): stops where every paused term was marked
-- "I already know this". Terms sharing a pause_ts are one stop.
WITH paused AS (
    SELECT DISTINCT e.learner_id, e.term_id
    FROM events e JOIN learners l ON l.id = e.learner_id
    WHERE e.type = 'pause' AND l.token_hash IS NOT NULL
),
stops AS (
    SELECT p.learner_id,
           bool_and(EXISTS (SELECT 1 FROM events k
                            WHERE k.learner_id = p.learner_id AND k.term_id = p.term_id AND k.type = 'known')) AS all_known
    FROM paused p JOIN terms t ON t.id = p.term_id
    GROUP BY p.learner_id, t.video_id, t.pause_ts
)
SELECT learner_id, count(*) AS stops, count(*) FILTER (WHERE all_known) AS pointless_stops
FROM stops
GROUP BY ROLLUP (learner_id)
ORDER BY learner_id NULLS LAST;

-- 3. Each learner's skipped terms, to set beside their survey Q5 answer (which of these were unfamiliar?).
SELECT lt.learner_id, t.term, lt.source
FROM learner_terms lt
JOIN learners l ON l.id = lt.learner_id
JOIN terms t ON lower(t.term) = lt.term_text
WHERE l.token_hash IS NOT NULL AND lt.status = 'known' AND lt.source IN ('questionnaire', 'notes')
  AND t.video_id IN (SELECT video_id FROM events e WHERE e.learner_id = lt.learner_id)
ORDER BY lt.learner_id, t.pause_ts;
