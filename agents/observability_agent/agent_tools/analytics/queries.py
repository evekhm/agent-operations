"""
Centralized templates for all standardized analytical SQL queries across the ADK Observability Agent.
This ensures all metrics rely on uniform aggregation, sorting, and reporting schemas without duplicating raw SQL text across Python modules.
"""

from ...config import PROJECT_ID, DATASET_ID, LLM_EVENTS_VIEW_ID, AGENT_EVENTS_VIEW_ID, INVOCATION_EVENTS_VIEW_ID
from ...prompts import ROOT_CAUSE_ANALYSIS_PROMPT

# =====================================================================
# EVENT FETCHING TEMPLATES
# =====================================================================

GET_PAGINATED_EVENTS_QUERY = f"""
SELECT 
    {{specific_columns}},
    {{common_columns}}
FROM `{PROJECT_ID}.{DATASET_ID}.{{view_id}}` AS T
{{joins}}
WHERE {{where_clause}}
ORDER BY {{order_clause}}
LIMIT {{limit}}
"""

ANALYZE_ERROR_CATEGORIES_QUERY = f"""
SELECT
    CASE
        WHEN LOWER(error_message) LIKE '%quota%' OR LOWER(error_message) LIKE '%rate limit%' THEN 'QUOTA_EXCEEDED'
        WHEN LOWER(error_message) LIKE '%timeout%' OR LOWER(error_message) LIKE '%deadline%' OR LOWER(error_message) LIKE '%timed out%' THEN 'TIMEOUT'
        WHEN LOWER(error_message) LIKE '%permission%' OR LOWER(error_message) LIKE '%unauthorized%' OR LOWER(error_message) LIKE '%403%' THEN 'PERMISSION_DENIED'
        WHEN LOWER(error_message) LIKE '%model%' OR LOWER(error_message) LIKE '%generation%' OR LOWER(error_message) LIKE '%500%' THEN 'MODEL_ERROR'
        WHEN LOWER(error_message) LIKE '%not found%' AND LOWER(error_message) LIKE '%tool%' THEN 'TOOL_NOT_FOUND'
        WHEN LOWER(error_message) LIKE '%tool%' OR LOWER(error_message) LIKE '%function%' THEN 'TOOL_ERROR'
        WHEN LOWER(error_message) LIKE '%parse%' OR LOWER(error_message) LIKE '%json%' THEN 'PARSING_ERROR'
        ELSE 'OTHER_ERROR'
    END as category,
    COUNT(*) as total_count
FROM `{PROJECT_ID}.{DATASET_ID}.{{view_id}}` AS T
WHERE {{where_clause}} AND status = 'ERROR'
GROUP BY category
ORDER BY total_count DESC
"""

GET_RAW_INVOCATIONS_QUERY = f"""
SELECT
    root_agent_name as agent_name,
    duration_ms,
    timestamp
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
  AND duration_ms > 0
ORDER BY timestamp DESC, duration_ms DESC, agent_name ASC
LIMIT {{limit}}
"""

GET_RAW_AGENTS_QUERY = f"""
WITH Agents AS (
    SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS T WHERE {{where_clause}}
)
SELECT
    A.span_id,
    A.agent_name,
    L.model_name,
    A.duration_ms,
    A.timestamp
FROM Agents AS A
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS L
  ON A.trace_id = L.trace_id AND A.span_id = L.parent_span_id
WHERE A.duration_ms > 0
  AND A.agent_name != A.root_agent_name
ORDER BY A.timestamp DESC, A.span_id ASC
LIMIT {{limit}}
"""

GET_LATENCY_DISTRIBUTION_QUERY = f"""
WITH LatencyData AS (
    SELECT {{latency_col}} as latency_ms
    FROM `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
    WHERE {{where_clause}} AND {{latency_col}} > 0
),
Percentiles AS (
    SELECT
        APPROX_QUANTILES(latency_ms, 100)[OFFSET(5)] as p05,
        APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] as p95
    FROM LatencyData
),
FilteredData AS (
    SELECT latency_ms
    FROM LatencyData
    CROSS JOIN Percentiles
    WHERE latency_ms BETWEEN p05 AND p95
)
SELECT
    COUNT(latency_ms) as count,
    MIN(latency_ms) as min_val,
    MAX(latency_ms) as max_val,
    AVG(latency_ms) as mean
FROM FilteredData
"""

GET_LATENCY_PERFORMANCE_QUERY = f"""
SELECT
    {{group_clause_final}}
    COUNT(*) as total_count,
    COUNTIF(status = 'ERROR') as error_count,
    COUNTIF(status != 'ERROR' AND status != 'PENDING') as success_count,
    ROUND(COUNTIF(status = 'ERROR') / NULLIF(COUNTIF(status != 'PENDING'), 0) * 100, 2) as error_rate_pct,
    AVG(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as avg_ms,
    STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as std_latency_ms,
    ROUND((STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) / NULLIF(AVG(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)), 0)) * 100, 2) as cv_pct,
    MIN(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as min_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(500)] as p50_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(750)] as p75_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(900)] as p90_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(950)] as p95_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(990)] as p99_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(999)] as p999_ms,
    MAX(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as max_ms
    {{optional_token_metrics}}
FROM
    `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
WHERE
    {{where_clause}}
GROUP BY {{group_clause_final}}
ORDER BY avg_ms DESC, total_count DESC
"""

GET_ACTIVE_METADATA_QUERY = f"""
SELECT DISTINCT {{column_name}}
FROM `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
WHERE {{where_clause}} AND {{column_name}} IS NOT NULL
LIMIT {{limit}}
"""

ANALYZE_ROOT_CAUSE_QUERY = f"""
SELECT
    {{id_column}} AS span_id,
    AI.GENERATE(
        ('{ROOT_CAUSE_ANALYSIS_PROMPT}', TO_JSON_STRING(T)),
        connection_id => '{{connection_id}}',
        endpoint => '{{model_endpoint}}'
    ).result AS analysis
FROM `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
WHERE {{id_column}} = '{{span_id}}'
"""

GET_BASELINE_PERFORMANCE_QUERY = f"""
WITH RankedData AS (
    SELECT
        {{group_by}} as group_key,
        {{latency_col}} as latency_ms,
        PERCENT_RANK() OVER (PARTITION BY {{group_by}} ORDER BY {{latency_col}} ASC) as percentile_rank
    FROM `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
    WHERE {{where_clause}} AND {{latency_col}} > 50
),
FilteredBaseline AS (
    SELECT group_key, latency_ms
    FROM RankedData
    WHERE percentile_rank <= {{limit_percentile}}
)
SELECT
    group_key,
    COUNT(*) as baseline_sample_size,
    AVG(latency_ms) as target_mean_ms,
    APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] as target_p95_ms
FROM FilteredBaseline
GROUP BY group_key
ORDER BY target_mean_ms ASC, group_key ASC
"""

ANALYZE_LATENCY_TREND_QUERY = f"""
SELECT
    {{group_by}} AS name,
    TIMESTAMP_TRUNC(timestamp, {{bq_interval}}) AS time_bucket,
    COUNT(*) AS total_calls,
    APPROX_QUANTILES(duration_ms, 100)[OFFSET(95)] AS p95_ms,
    AVG(duration_ms) AS avg_ms,
    COUNTIF(status = 'ERROR') / NULLIF(COUNT(*), 0) * 100 AS error_rate_pct
FROM
    `{PROJECT_ID}.{DATASET_ID}.{{view_id}}`
WHERE
    {{clean_where_clause}}
GROUP BY
    name, time_bucket
ORDER BY
    name, time_bucket ASC
"""

GET_LATENCY_GROUPED_JOINED_QUERY = f"""
WITH LLM_Aggregated AS (
    SELECT 
        parent_span_id, 
        model_name,
        SUM(prompt_token_count) as prompt_token_count,
        SUM(candidates_token_count) as candidates_token_count,
        SUM(thoughts_token_count) as thoughts_token_count,
        SUM(total_token_count) as total_token_count
    FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}`
    GROUP BY 1, 2
)
SELECT
  {{select_group_sql}},
  COUNT(DISTINCT A.span_id) as total_count,
  COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) as error_count,
  COUNT(DISTINCT CASE WHEN A.status != 'ERROR' AND A.status != 'PENDING' THEN A.span_id END) as success_count,
  ROUND(COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) / NULLIF(COUNT(DISTINCT A.span_id), 0) * 100, 2) as error_rate_pct,
  AVG(A.{{latency_col}}) as avg_ms,
  STDDEV(A.{{latency_col}}) as std_latency_ms,
  0.0 as cv_pct, -- approximation
  MIN(A.{{latency_col}}) as min_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(500)] as p50_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(750)] as p75_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(900)] as p90_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(950)] as p95_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(990)] as p99_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(999)] as p999_ms,
  APPROX_QUANTILES(A.{{latency_col}}, 1000)[OFFSET(CAST({{percentile}} * 10 AS INT64))] as p_custom_ms,
  MAX(A.{{latency_col}}) as max_ms,
  -- Token Metrics
  AVG(L.prompt_token_count) as avg_input_tokens,
  APPROX_QUANTILES(L.prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
  AVG(L.candidates_token_count) as avg_output_tokens,
  APPROX_QUANTILES(L.candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
  APPROX_QUANTILES(L.candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
  MIN(L.candidates_token_count) as min_output_tokens,
  MAX(L.candidates_token_count) as max_output_tokens,
  AVG(L.thoughts_token_count) as avg_thought_tokens,
  APPROX_QUANTILES(L.thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens,
  AVG(L.total_token_count) as avg_total_tokens,
  APPROX_QUANTILES(L.total_token_count, 100)[OFFSET(95)] as p95_total_tokens,
  -- Correlation Metrics
  CORR(A.{{latency_col}}, L.candidates_token_count - IFNULL(L.thoughts_token_count, 0)) as corr_latency_pure_output,
  CORR(A.{{latency_col}}, L.candidates_token_count) as corr_latency_output_plus_thoughts,
  CORR(A.{{latency_col}}, L.total_token_count) as corr_latency_total
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` AS A
JOIN LLM_Aggregated AS L
ON A.span_id = L.parent_span_id
WHERE {{where_clause_joined}}
GROUP BY {{group_by_sql}}
ORDER BY avg_ms DESC, total_count DESC
"""

GET_LATENCY_GROUPED_BASE_QUERY = f"""
SELECT
  {{select_group_cols}},
  COUNT(*) as total_count,
  COUNTIF(status = 'ERROR') as error_count,
  COUNTIF(status != 'ERROR' AND status != 'PENDING') as success_count,
  ROUND(COUNTIF(status = 'ERROR') / NULLIF(COUNTIF(status != 'PENDING'), 0) * 100, 2) as error_rate_pct,
  AVG(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as avg_ms,
  STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as std_latency_ms,
  ROUND((STDDEV(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) / NULLIF(AVG(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)), 0)) * 100, 2) as cv_pct,
  MIN(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as min_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(500)] as p50_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(750)] as p75_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(900)] as p90_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(950)] as p95_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(990)] as p99_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(999)] as p999_ms,
  APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL), 1000)[OFFSET(CAST({{percentile}} * 10 AS INT64))] as p_custom_ms,
  MAX(IF(status != 'ERROR' AND status != 'PENDING', {{latency_col}}, NULL)) as max_ms
  {{optional_token_metrics}}
FROM
  `{PROJECT_ID}.{DATASET_ID}.{{target_table}}` AS T
WHERE
  {{where_clause}}
GROUP BY {{group_by_clause}}
ORDER BY avg_ms DESC, total_count DESC
"""

GET_LATENCY_GROUPED_TOKEN_QUERY = f"""
SELECT
  {{select_group_cols}},
  AVG(prompt_token_count) as avg_input_tokens,
  APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
  AVG(candidates_token_count) as avg_output_tokens,
  APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
  APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
  MIN(candidates_token_count) as min_output_tokens,
  MAX(candidates_token_count) as max_output_tokens,
  AVG(thoughts_token_count) as avg_thought_tokens,
  APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens,
  AVG(total_token_count) as avg_total_tokens,
  APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
GROUP BY {{group_by_clause}}
"""

ANALYZE_LATENCY_GROUPS_QUERY = f"""
SELECT
  T.agent_name,
  T.root_agent_name,
  T.model_name,
  COUNT(*) as count,
  AVG(duration_ms) as avg_latency_ms,
  MIN(duration_ms) as min_latency_ms,
  MAX(duration_ms) as max_latency_ms,
  STDDEV(duration_ms) as std_latency_ms
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
GROUP BY root_agent_name, agent_name, model_name
ORDER BY count DESC, avg_latency_ms DESC, agent_name ASC, model_name ASC
LIMIT {{limit}}
"""

GET_CONCURRENT_REQUEST_IMPACT_QUERY = f"""
WITH ConcurrencyCounts AS (
    SELECT
        TIMESTAMP_TRUNC(timestamp, MINUTE) as time_bucket,
        COUNT(*) as concurrent_requests,
        AVG(duration_ms) as avg_latency_in_bucket
    FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
    WHERE {{where_clause}}
    GROUP BY time_bucket
)
SELECT
    concurrent_requests,
    AVG(avg_latency_in_bucket) as avg_latency_for_level,
    COUNT(*) as occurrences
FROM ConcurrencyCounts
GROUP BY concurrent_requests
ORDER BY concurrent_requests ASC
"""

ANALYZE_REQUEST_QUEUING_QUERY = f"""
WITH Bursts AS (
     SELECT
        TIMESTAMP_TRUNC(timestamp, SECOND) as second_bucket,
        COUNT(*) as requests_per_second
     FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
     WHERE {{where_clause}}
     GROUP BY second_bucket
     HAVING requests_per_second > 1
)
SELECT
    requests_per_second,
    COUNT(*) as burst_count
FROM Bursts
GROUP BY requests_per_second
ORDER BY requests_per_second DESC
"""

GET_CONFIG_OUTLIERS_QUERY = f"""
SELECT
    agent_name,
    model_name,
    {{config_select_str}},
    AVG(duration_ms) as avg_latency,
    STDDEV(duration_ms) as stddev_latency,
    COUNT(*) as request_count
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
GROUP BY {{group_by_str}}
HAVING request_count > 5
ORDER BY avg_latency DESC, request_count DESC, agent_name ASC, model_name ASC
LIMIT {{limit}}
"""

FETCH_SINGLE_QUERY = f"""
SELECT
  T.timestamp,
  T.span_id,
  T.full_request,
  T.full_response,
  T.model_name,
  T.agent_name,
  T.duration_ms,
  T.thoughts_token_count,
  T.candidates_token_count AS output_token_count,
  T.prompt_token_count,
  T.total_token_count
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE CAST(T.span_id AS STRING) = @span_id
LIMIT 1
"""

ANALYZE_EMPTY_RESPONSES_SUMMARY_QUERY = f"""
SELECT
    model_name,
    agent_name,
    COUNT(*) as empty_response_count
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
GROUP BY model_name, agent_name
ORDER BY empty_response_count DESC, agent_name ASC, model_name ASC
"""

ANALYZE_EMPTY_RESPONSES_RECORDS_QUERY = f"""
SELECT
    T.span_id,
    T.trace_id,
    T.timestamp,
    T.model_name,
    T.agent_name,
    T.prompt_token_count,
    T.duration_ms,
    I.content_text_summary
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW_ID}` I ON T.trace_id = I.trace_id
WHERE {{where_clause}}
ORDER BY timestamp DESC, T.trace_id ASC, T.span_id ASC
LIMIT {{limit}}
"""

FETCH_CORRELATION_DATA_QUERY = f"""
SELECT
    root_agent_name,
    agent_name,
    model_name,
    total_token_count,
    prompt_token_count,
    candidates_token_count,
    thoughts_token_count,
    duration_ms,
    timestamp,
    time_to_first_token_ms
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW_ID}` AS T
WHERE {{where_clause}}
  AND total_token_count > 0
  AND duration_ms > 0
ORDER BY timestamp DESC, root_agent_name ASC, agent_name ASC
LIMIT {{limit}}
"""

GET_OUTLIER_THRESHOLD_QUERY = f"""
SELECT APPROX_QUANTILES({{metric}}, 100)[OFFSET({{percentile_offset}})] as threshold
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
WHERE {{where_clause}} AND T.parent_span_id IS NULL
"""

GET_OUTLIER_RECORDS_QUERY = f"""
SELECT 
    T.agent_name,
    T.model_name,
    T.input_token_count,
    T.output_token_count,
    T.total_token_count,
    T.duration_ms,
    T.status,
    T.trace_id
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW_ID}` T
WHERE {{where_clause}} 
AND T.parent_span_id IS NULL
AND T.{{metric}} >= {{threshold_val}}
ORDER BY T.{{metric}} DESC, T.trace_id ASC
LIMIT {{limit}}
"""
