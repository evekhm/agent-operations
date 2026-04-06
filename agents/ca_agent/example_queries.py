from google.cloud import geminidataanalytics
from config import PROJECT_ID, DATASET_ID, TABLE_ID, AGENT_EVENTS_VIEW, INVOCATION_EVENTS_VIEW, TOOL_EVENTS_VIEW, LLM_EVENTS_VIEW

def generate_latency_query(dimension: str, view_name: str, extra_filters: str = "", include_token_metrics: bool = False, group_by: str = "1") -> str:
    where_clause = f"T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'"
    if extra_filters:
        where_clause += f" AND {extra_filters}"
        
    token_metrics_sql = ""
    if include_token_metrics:
        token_metrics_sql = """
    , AVG(prompt_token_count) as avg_input_tokens,
    APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] as p95_input_tokens,
    AVG(candidates_token_count) as avg_output_tokens,
    APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] as p95_output_tokens,
    APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(50)] as median_output_tokens,
    MIN(candidates_token_count) as min_output_tokens,
    MAX(candidates_token_count) as max_output_tokens,
    AVG(thoughts_token_count) as avg_thought_tokens,
    APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] as p95_thought_tokens,
    AVG(total_token_count) as avg_total_tokens,
    APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens,
    CORR(duration_ms, prompt_token_count) as corr_latency_input,
    CORR(duration_ms, candidates_token_count) as corr_latency_output,
    CORR(duration_ms, total_token_count) as corr_latency_total
"""

    return f"""
SELECT
    {dimension},
    COUNT(*) as total_count,
    COUNTIF(status = 'ERROR') as error_count,
    COUNTIF(status != 'ERROR' AND status != 'PENDING') as success_count,
    ROUND(COUNTIF(status = 'ERROR') / NULLIF(COUNTIF(status != 'PENDING'), 0) * 100, 2) as error_rate_pct,
    AVG(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as avg_ms,
    STDDEV(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as std_latency_ms,
    ROUND((STDDEV(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) / NULLIF(AVG(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)), 0)) * 100, 2) as cv_pct,
    MIN(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as min_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(500)] as p50_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(750)] as p75_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(900)] as p90_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(950)] as p95_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(990)] as p99_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(999)] as p999_ms,
    APPROX_QUANTILES(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL), 1000)[OFFSET(CAST(95.5 * 10 AS INT64))] as p_custom_ms,
    MAX(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as max_ms
    {token_metrics_sql}
FROM
    `{PROJECT_ID}.{DATASET_ID}.{view_name}` AS T
WHERE
    {where_clause}
GROUP BY {group_by}
ORDER BY avg_ms DESC, total_count DESC
"""

def generate_token_stats_query(dimension: str, extra_filters: str = "", group_by: str = "1") -> str:
    where_clause = f"T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()"
    if extra_filters:
        where_clause += f" AND {extra_filters}"
        
    return f"""
SELECT
    {dimension},
    AVG(prompt_token_count) AS avg_input_tokens,
    APPROX_QUANTILES(prompt_token_count, 100)[OFFSET(95)] AS p95_input_tokens,
    AVG(candidates_token_count) AS avg_output_tokens,
    APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(95)] AS p95_output_tokens,
    APPROX_QUANTILES(candidates_token_count, 100)[OFFSET(50)] AS median_output_tokens,
    MIN(candidates_token_count) AS min_output_tokens,
    MAX(candidates_token_count) AS max_output_tokens,
    AVG(thoughts_token_count) AS avg_thought_tokens,
    APPROX_QUANTILES(thoughts_token_count, 100)[OFFSET(95)] AS p95_thought_tokens,
    AVG(total_token_count) AS avg_total_tokens,
    APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] AS p95_total_tokens
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE {where_clause}
GROUP BY {group_by}
"""

example_queries = [
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by root agent",
        sql_query=generate_latency_query("agent_name", AGENT_EVENTS_VIEW, "agent_name != root_agent_name"),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by invocation",
        sql_query=generate_latency_query("root_agent_name", INVOCATION_EVENTS_VIEW),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by tool",
        sql_query=generate_latency_query("tool_name", TOOL_EVENTS_VIEW, "tool_name != 'transfer_to_agent'"),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by LLM",
        sql_query=generate_latency_query("model_name", LLM_EVENTS_VIEW, include_token_metrics=True),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by agent",
        sql_query=f"""
WITH LLM_Aggregated AS (
    SELECT
        parent_span_id,
        model_name,
        SUM(prompt_token_count) as prompt_token_count,
        SUM(candidates_token_count) as candidates_token_count,
        SUM(thoughts_token_count) as thoughts_token_count,
        SUM(total_token_count) as total_token_count
    FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}`
    GROUP BY 1, 2
)
SELECT
    A.agent_name,
    L.model_name,
    COUNT(DISTINCT A.span_id) as total_count,
    COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) as error_count,
    COUNT(DISTINCT CASE WHEN A.status != 'ERROR' AND A.status != 'PENDING' THEN A.span_id END) as success_count,
    ROUND(COUNT(DISTINCT CASE WHEN A.status = 'ERROR' THEN A.span_id END) / NULLIF(COUNT(DISTINCT A.span_id), 0) * 100, 2) as error_rate_pct,
    AVG(A.duration_ms) as avg_ms,
    STDDEV(A.duration_ms) as std_latency_ms,
    0.0 as cv_pct, -- approximation
    MIN(A.duration_ms) as min_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(500)] as p50_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(750)] as p75_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(900)] as p90_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(950)] as p95_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(990)] as p99_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(999)] as p999_ms,
    APPROX_QUANTILES(A.duration_ms, 1000)[OFFSET(CAST(95.5 * 10 AS INT64))] as p_custom_ms,
    MAX(A.duration_ms) as max_ms,
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
    CORR(A.duration_ms, L.prompt_token_count) as corr_latency_input,
    CORR(A.duration_ms, L.candidates_token_count - IFNULL(L.thoughts_token_count, 0)) as corr_latency_pure_output,
    CORR(A.duration_ms, L.candidates_token_count) as corr_latency_output_plus_thoughts,
    CORR(A.duration_ms, L.total_token_count) as corr_latency_total
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS A
JOIN LLM_Aggregated AS L ON A.span_id = L.parent_span_id
WHERE A.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
GROUP BY 1, 2
ORDER BY avg_ms DESC, total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by LLM",
        sql_query=generate_latency_query("agent_name, model_name", LLM_EVENTS_VIEW, include_token_metrics=True, group_by="1, 2"),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show top slowest invocations",
        sql_query=f"""
SELECT
    T.content_text,
    T.content_text_summary,
    T.invocation_id,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.duration_ms DESC, T.timestamp DESC
LIMIT 10
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show top slowest sub-agent executions",
        sql_query=f"""
SELECT
    T.instruction,
    T.parent_span_id,
    I.status AS root_status,
    I.duration_ms AS root_duration_ms,
    I.content_text_summary,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS I
    ON T.trace_id = I.trace_id
WHERE T.agent_name != T.root_agent_name
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.duration_ms DESC, T.timestamp DESC
LIMIT 10
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show top slowest tool executions",
        sql_query=f"""
SELECT
    T.tool_name,
    T.tool_args,
    T.tool_result,
    T.parent_span_id,
    A.status AS agent_status,
    A.duration_ms AS agent_duration_ms,
    I.status AS root_status,
    I.duration_ms AS root_duration_ms,
    I.content_text_summary,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS I
    ON T.trace_id = I.trace_id
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS A
    ON T.parent_span_id = A.span_id
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND tool_name NOT IN ('transfer_to_agent')
ORDER BY T.duration_ms DESC, T.timestamp DESC
LIMIT 10
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show top slowest LLM calls with full context",
        sql_query=f"""
SELECT
    T.model_name,
    T.prompt_token_count,
    T.candidates_token_count,
    T.total_token_count,
    T.thoughts_token_count,
    T.time_to_first_token_ms,
    T.full_request,
    T.full_response,
    T.llm_config,
    T.parent_span_id,
    T.response_text,
    A.status AS agent_status,
    A.duration_ms AS agent_duration_ms,
    I.status AS root_status,
    I.duration_ms AS root_duration_ms,
    I.content_text_summary,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS I
    ON T.trace_id = I.trace_id
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS A
    ON T.parent_span_id = A.span_id
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.duration_ms DESC, T.timestamp DESC
LIMIT 10
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show invocation requests",
        sql_query=f"""SELECT      T.content_text,     T.content_text_summary,     T.invocation_id,     T.trace_id,     T.span_id,     T.session_id,     T.duration_ms,     T.agent_name,     T.root_agent_name,     T.status,     T.timestamp,     T.error_message FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T  WHERE T.status = 'ERROR' AND T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13' ORDER BY T.timestamp DESC LIMIT 1000000""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show failed invocations with detail",
        sql_query=f"""
SELECT
    T.content_text,
    T.content_text_summary,
    T.invocation_id,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.timestamp DESC
LIMIT 1000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show failed sub-agent executions with detail",
        sql_query=f"""
SELECT
    T.instruction,
    T.parent_span_id,
    I.status AS root_status,
    I.duration_ms AS root_duration_ms,
    I.content_text_summary,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS I
    ON T.trace_id = I.trace_id
WHERE T.agent_name != T.root_agent_name
    AND T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.timestamp DESC
LIMIT 1000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show failed LLM calls with full context",
        sql_query=f"""
SELECT
    T.model_name,
    T.prompt_token_count,
    T.candidates_token_count,
    T.total_token_count,
    T.thoughts_token_count,
    T.time_to_first_token_ms,
    T.full_request,
    T.full_response,
    T.llm_config,
    T.parent_span_id,
    T.response_text,
    A.status AS agent_status,
    A.duration_ms AS agent_duration_ms,
    I.status AS root_status,
    I.duration_ms AS root_duration_ms,
    I.content_text_summary,
    T.trace_id,
    T.span_id,
    T.session_id,
    T.duration_ms,
    T.agent_name,
    T.root_agent_name,
    T.status,
    T.timestamp,
    T.error_message
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS I
    ON T.trace_id = I.trace_id
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS A
    ON T.parent_span_id = A.span_id
WHERE T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
ORDER BY T.timestamp DESC
LIMIT 1000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show empty LLM responses summary by agent and model",
        sql_query=f"""
SELECT
    model_name,
    agent_name,
    CASE
        WHEN T.response_text IS NULL OR TRIM(T.response_text) = '' THEN 'Response Text is NULL'
        ELSE 'Response Text is POPULATED'
    END AS response_type,
    COUNT(*) AS empty_response_count
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND (IFNULL(T.candidates_token_count, 0) = 0 OR T.response_text IS NULL OR T.response_text = '')
    AND T.status != 'ERROR'
GROUP BY model_name, agent_name, response_type
ORDER BY response_type ASC, empty_response_count DESC, agent_name ASC, model_name ASC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show hallucination loops (runaway token generation)",
        sql_query=f"""
SELECT
    T.trace_id,
    T.span_id,
    T.agent_name,
    T.model_name,
    T.candidates_token_count,
    T.duration_ms,
    I.content_text_summary,
    T.response_text,
    T.timestamp
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` I
    ON T.trace_id = I.trace_id
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND T.candidates_token_count > 8000
    AND T.duration_ms > 120000
QUALIFY ROW_NUMBER() OVER(PARTITION BY T.trace_id, T.span_id ORDER BY T.timestamp DESC) = 1
ORDER BY T.candidates_token_count DESC
LIMIT 100
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token and latency correlation data for analysis",
        sql_query=f"""
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
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND total_token_count > 0
    AND duration_ms > 0
ORDER BY timestamp DESC, root_agent_name ASC, agent_name ASC
LIMIT 100000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show raw invocation latency data over time",
        sql_query=f"""
SELECT
    root_agent_name AS agent_name,
    duration_ms,
    timestamp
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND duration_ms > 0
ORDER BY timestamp DESC, duration_ms DESC, agent_name ASC
LIMIT 100000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show raw sub-agent latency data with model attribution",
        sql_query=f"""
WITH Agents AS (
    SELECT *
    FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
    WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
)
SELECT
    A.span_id,
    A.agent_name,
    L.model_name,
    A.duration_ms,
    A.timestamp
FROM Agents AS A
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS L
    ON A.trace_id = L.trace_id AND A.span_id = L.parent_span_id
WHERE A.duration_ms > 0
    AND A.agent_name != A.root_agent_name
ORDER BY A.timestamp DESC, A.span_id ASC
LIMIT 100000
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by root agent",
        sql_query=generate_token_stats_query("root_agent_name"),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by sub-agent",
        sql_query=generate_token_stats_query("agent_name", "agent_name != root_agent_name"),
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show empty LLM response rows with full detail",
        sql_query=f"""
SELECT
    T.span_id,
    T.trace_id,
    T.timestamp,
    T.status,
    T.model_name,
    T.agent_name,
    T.prompt_token_count,
    T.thoughts_token_count,
    T.candidates_token_count,
    T.duration_ms,
    T.response_text,
    T.full_response,
    I.content_text_summary
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` I
    ON T.trace_id = I.trace_id
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND (IFNULL(T.candidates_token_count, 0) = 0 OR T.response_text IS NULL OR T.response_text = '')
    AND T.status != 'ERROR'
ORDER BY timestamp DESC, T.trace_id ASC, T.span_id ASC
LIMIT 100
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by agent and model",
        sql_query=generate_token_stats_query("agent_name, model_name", group_by="1, 2"),
    ),
]

glossary_terms = [
    geminidataanalytics.GlossaryTerm(
        display_name="Session",
        description="A single conversation thread between a user and the agent, identified by session_id.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Invocation",
        description="A single request-response cycle within a session (one turn), identified by invocation_id. Generally corresponds to a user clicking 'send'.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Agent Execution",
        description="A period where an agent (root or sub-agent) is running. Identified by a span. One invocation can trigger multiple agent executions in a hierarchy.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Tool Execution",
        description="The running of a specific capability (e.g., querying a database, searching the web).",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="LLM Call",
        description="A request sent to a Large Language Model and the corresponding response.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Status PENDING",
        description="Indicates that an operation (invocation, agent, or tool) has started but has not yet completed. If an operation remains PENDING for longer than a configured timeout (e.g., 5 minutes), it may be interpreted as an error or crash.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Status OK",
        description="The operation completed successfully.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="Status ERROR",
        description="The operation failed.",
    ),
]

new_example_queries = [
    geminidataanalytics.ExampleQuery(
        natural_language_question="Trace a specific conversation turn using trace_id",
        sql_query=f"""SELECT timestamp, event_type, agent, JSON_VALUE(content, '$.response') as summary FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE trace_id = 'your-trace-id' ORDER BY timestamp ASC;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Token usage analysis (accessing JSON fields)",
        sql_query=f"""SELECT AVG(CAST(JSON_VALUE(content, '$.usage.total') AS INT64)) as avg_tokens FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE event_type = 'LLM_RESPONSE';""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Querying Multimodal Content (using content_parts and ObjectRef)",
        sql_query=f"""SELECT timestamp, part.mime_type, part.object_ref.uri as gcs_uri FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`, UNNEST(content_parts) as part WHERE part.mime_type LIKE 'image/%' ORDER BY timestamp DESC;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze Multimodal Content with BigQuery Remote Model (Gemini)",
        sql_query=f"""SELECT logs.session_id, STRING(OBJ.GET_ACCESS_URL(parts.object_ref, "r").access_urls.read_url) as signed_url, AI.GENERATE( ('Describe this image briefly. What company logo?', parts.object_ref) ) AS generated_result FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` logs, UNNEST(logs.content_parts) AS parts WHERE parts.mime_type LIKE 'image/%' ORDER BY logs.timestamp DESC LIMIT 1;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Latency Analysis (LLM & Tools)",
        sql_query=f"""SELECT event_type, AVG(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64)) as avg_latency_ms FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE event_type IN ('LLM_RESPONSE', 'TOOL_COMPLETED') GROUP BY event_type;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Span Hierarchy & Duration Analysis",
        sql_query=f"""SELECT span_id, parent_span_id, event_type, timestamp, CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64) as duration_ms, COALESCE( JSON_VALUE(content, '$.tool'), 'LLM_CALL' ) as operation FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE trace_id = 'your-trace-id' AND event_type IN ('LLM_RESPONSE', 'TOOL_COMPLETED') ORDER BY timestamp ASC;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Error Analysis (LLM & Tool Errors)",
        sql_query=f"""SELECT timestamp, event_type, agent, error_message, JSON_VALUE(content, '$.tool') as tool_name, CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64) as latency_ms FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE event_type IN ('LLM_ERROR', 'TOOL_ERROR') ORDER BY timestamp DESC LIMIT 20;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Tool Provenance Analysis",
        sql_query=f"""SELECT JSON_VALUE(content, '$.tool_origin') as tool_origin, JSON_VALUE(content, '$.tool') as tool_name, COUNT(*) as call_count, AVG(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64)) as avg_latency_ms FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE event_type = 'TOOL_COMPLETED' GROUP BY tool_origin, tool_name ORDER BY call_count DESC;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="HITL Interaction Analysis",
        sql_query=f"""SELECT timestamp, event_type, session_id, JSON_VALUE(content, '$.tool') as hitl_tool, content FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE event_type LIKE 'HITL_%' ORDER BY timestamp DESC LIMIT 20;""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="AI-Powered Root Cause Analysis (Agent Ops)",
        sql_query=f"""
WITH failed_session AS (
    SELECT session_id
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
    WHERE error_message IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT 1
),
SessionContext AS (
    SELECT
        s.session_id,
        STRING_AGG(
            CONCAT(e.event_type, ': ', COALESCE(TO_JSON_STRING(e.content), '')),
            '\\n' ORDER BY e.timestamp
        ) AS full_history
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` AS e
    JOIN failed_session AS s ON e.session_id = s.session_id
    GROUP BY s.session_id
)
SELECT
    session_id,
    AI.GENERATE(
        ('Analyze this conversation log and explain the root cause of the failure. Log: ', full_history),
        endpoint => 'gemini-2.5-flash'
    ).result AS root_cause_explanation
FROM SessionContext
""",
    ),
]

example_queries += new_example_queries
