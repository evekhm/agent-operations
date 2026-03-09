/*
 * LLM Events View
 * ---------------
 * Isolates LLM interactions (requests and responses) from the raw event stream.
 */
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.llm_events_view` (
    timestamp OPTIONS(description="The timestamp of the LLM_REQUEST event. Used as the primary time-series anchor."),
    root_agent_name OPTIONS(description="The name of the root agent that initiated the invocation."),
    agent_name OPTIONS(description="The name of the agent that made the LLM call."),
    llm_config OPTIONS(description="JSON representation of the LLM configuration (temperature, top_p, etc.)."),
    usage_metadata OPTIONS(description="JSON representation of token usage metrics."),
    model_name OPTIONS(description="The model name, preferring the specific version from the response if available, otherwise the requested model."),
    requested_model OPTIONS(description="The model name requested in the LLM_REQUEST event."),
    response_model OPTIONS(description="The specific model version returned in the LLM_RESPONSE event."),
    duration_ms OPTIONS(description="The total time in milliseconds for the LLM call."),
    time_to_first_token_ms OPTIONS(description="The time in milliseconds until the first token was received (for streaming responses)."),
    status OPTIONS(description="The outcome of the LLM call. 'OK' on success, 'ERROR' on failure."),
    error_message OPTIONS(description="The exception message if the LLM call failed."),
    prompt_token_count OPTIONS(description="The number of tokens in the input prompt."),
    candidates_token_count OPTIONS(description="The number of tokens generated in the response."),
    total_token_count OPTIONS(description="The total number of tokens (prompt + candidates)."),
    thoughts_token_count OPTIONS(description="The number of tokens used for thinking/reasoning steps."),
    full_request OPTIONS(description="The raw JSON content of the LLM request."),
    full_response OPTIONS(description="The raw JSON content of the LLM response."),
    request_text OPTIONS(description="The extracted text portion of the user prompt sent to the model."),
    response_text OPTIONS(description="The extracted text portion of the model's response."),
    span_id OPTIONS(description="The OpenTelemetry span_id identifying this specific LLM call."),
    trace_id OPTIONS(description="The OpenTelemetry trace_id tying this call back to the root invocation."),
    parent_span_id OPTIONS(description="The span_id of the operation that made this LLM call."),
    user_id OPTIONS(description="The ID of the user who initiated the run."),
    session_id OPTIONS(description="The ID of the multi-turn session."),
    start_timestamp OPTIONS(description="The exact timestamp of the LLM_REQUEST event."),
    end_timestamp OPTIONS(description="The exact timestamp of the LLM_RESPONSE or LLM_ERROR event.")
) AS
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