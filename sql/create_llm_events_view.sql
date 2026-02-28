/*
 * LLM Events View
 * ---------------
 * Isolates LLM interactions (requests and responses) from the raw event stream.
 */
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.llm_events_view` AS
WITH LlmRequests AS (
  SELECT
    trace_id,
    span_id,
    parent_span_id,
    timestamp as start_timestamp,
    JSON_VALUE(attributes, '$.model') as model,
    JSON_QUERY(attributes, '$.llm_config') as llm_config,
    content as request_content,
    attributes as request_attributes,
    content_parts as request_content_parts,
    user_id,
    session_id,
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'LLM_REQUEST'
),
LlmResponses AS (
  SELECT
    trace_id,
    span_id,
    parent_span_id,
    timestamp as end_timestamp,
    content as response_content,
    attributes as response_attributes,
    error_message,
    status,
    event_type,
    -- Extract Metadata from Response Attributes
    JSON_VALUE(attributes, '$.model_version') AS model_version,
    JSON_VALUE(attributes, '$.root_agent_name') AS root_agent_name,
    JSON_QUERY(attributes, '$.usage_metadata') as usage_metadata,
    agent AS agent_name,
    SAFE_CAST(JSON_VALUE(TO_JSON_STRING(latency_ms), '$.total_ms') AS FLOAT64) AS duration_ms,
    SAFE_CAST(JSON_VALUE(TO_JSON_STRING(latency_ms), '$.time_to_first_token_ms') AS FLOAT64) AS time_to_first_token_ms,
    SAFE_CAST(JSON_VALUE(attributes, '$.usage_metadata.prompt_token_count') AS INT64) AS prompt_token_count,
    SAFE_CAST(JSON_VALUE(attributes, '$.usage_metadata.candidates_token_count') AS INT64) AS candidates_token_count,
    SAFE_CAST(JSON_VALUE(attributes, '$.usage_metadata.total_token_count') AS INT64) AS total_token_count,
    SAFE_CAST(JSON_VALUE(attributes, '$.usage_metadata.thoughts_token_count') AS INT64) AS thoughts_token_count,
    -- We don't select content_parts here because it is not populated for LLM_RESPONSE
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type IN ('LLM_RESPONSE', 'LLM_ERROR')
)
SELECT
    Req.start_timestamp as timestamp,
    R.root_agent_name,
    R.agent_name,

    Req.llm_config,
    R.usage_metadata,

    COALESCE(R.model_version, Req.model) AS model_name,
    Req.model AS requested_model,
    R.model_version AS response_model,

    R.duration_ms,
    R.time_to_first_token_ms,
    CASE
        WHEN R.event_type = 'LLM_ERROR' THEN 'ERROR'
        ELSE R.status
    END as status,
    R.error_message,

    R.prompt_token_count,
    R.candidates_token_count,
    R.total_token_count,
    R.thoughts_token_count,

    Req.request_content as full_request,
    R.response_content as full_response,

    -- Extract Request Text from content_parts (populated for LLM_REQUEST)
    (SELECT STRING_AGG(part.text, '\n') FROM UNNEST(Req.request_content_parts) AS part) AS request_text,

    -- Extract Response Text from response_content JSON (using Regex for 'text: ...' pattern)
    REGEXP_REPLACE(JSON_VALUE(R.response_content, '$.response'), r"^text: '(.*)'$", r"\1") AS response_text,

    R.span_id,
    R.trace_id,
    R.parent_span_id,
    Req.user_id,
    Req.session_id,

    Req.start_timestamp,
    R.end_timestamp,

FROM LlmResponses R
    LEFT JOIN LlmRequests Req ON R.span_id = Req.span_id AND R.trace_id = Req.trace_id;