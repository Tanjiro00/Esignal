SELECT id, started_at, completed_at, status,
       llm_trace_json->>'provider_calls' AS provider_calls,
       llm_trace_json->'task_calls' AS task_calls,
       llm_trace_json->'decisions' AS decisions
FROM topic_pipeline_runs
ORDER BY started_at DESC
LIMIT 5;

SELECT COALESCE(SUM(COALESCE((usage_json->>'total_tokens')::integer, 0)), 0)
           AS tokens_last_24h,
       MIN(created_at) AS oldest,
       MAX(created_at) AS newest
FROM llm_intelligence_runs
WHERE created_at >= now() - interval '24 hours'
  AND status IN ('success', 'rejected');

SELECT date_trunc('hour', created_at) AS hour,
       SUM(COALESCE((usage_json->>'total_tokens')::integer, 0)) AS tokens
FROM llm_intelligence_runs
WHERE created_at >= now() - interval '24 hours'
  AND status IN ('success', 'rejected')
GROUP BY 1
ORDER BY 1;
