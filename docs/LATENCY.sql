-- Model-call latency per provider, stage and model (roadmap #5). Run on the local database and on Neon
-- separately; they hold different calls, so report them side by side, never summed.
-- One row = one successful call, timed from the first attempt to the reply: it includes the rate-limit
-- wait, retries and backoff (pipeline/llm.py). Failed calls aren't logged, so p95 is slightly optimistic.
-- transcribe and embed write one row per video, not per call: read their n, not their percentiles.
-- Report p95 only where n >= 20; below that it is an interpolation between the slowest few calls.
SELECT CASE WHEN created_at < '2026-10-28 00:00+05:30' THEN 'token factory' ELSE 'deepinfra' END AS provider,
       stage,
       model,
       count(*) AS n,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) / 1000.0)::numeric, 1) AS p50_s,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) / 1000.0)::numeric, 1) AS p95_s,
       round(max(latency_ms) / 1000.0, 1) AS max_s
FROM stage_costs
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
