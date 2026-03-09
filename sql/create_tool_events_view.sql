/*
 * Tool Events View
 * ----------------
 * Specialized view for tool execution events (STARTING, COMPLETED, ERROR).
 * Normalizing for easier analysis of tool performance and reliability.
 * Joins TOOL_STARTING with corresponding TOOL_COMPLETED/TOOL_ERROR via span_id
 * to provide a consolidated view of latency, args, and results.
 *
 * Key Event Types:
 * - TOOL_STARTING: The invocation of a tool with specific arguments.
 * - TOOL_COMPLETED: The successful return of a tool execution.
 * - TOOL_ERROR: The failure/exception from a tool execution.
 */
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.tool_events_view` (
    timestamp OPTIONS(description="The timestamp of the TOOL_STARTING event. Used as the primary time-series anchor."),
    root_agent_name OPTIONS(description="The name of the root agent that initiated the invocation."),
    agent_name OPTIONS(description="The name of the agent executing the tool."),
    tool_name OPTIONS(description="The name of the executed tool."),
    tool_args OPTIONS(description="JSON representation of the arguments passed to the tool."),
    tool_result OPTIONS(description="JSON representation of the tool's result on success."),
    duration_ms OPTIONS(description="The total time in milliseconds for the tool execution."),
    error_message OPTIONS(description="The exception message if the tool call failed."),
    status OPTIONS(description="The execution status. 'OK' on success, 'ERROR' on failure, or 'PENDING' if the tool is still running or crashed."),
    span_id OPTIONS(description="The OpenTelemetry span_id identifying this specific tool execution."),
    trace_id OPTIONS(description="The OpenTelemetry trace_id tying this execution back to the root invocation."),
    parent_span_id OPTIONS(description="The span_id of the operation that called the tool."),
    user_id OPTIONS(description="The ID of the user who initiated the run."),
    session_id OPTIONS(description="The ID of the multi-turn session."),
    start_timestamp OPTIONS(description="The exact timestamp of the TOOL_STARTING event."),
    end_timestamp OPTIONS(description="The exact timestamp of the TOOL_COMPLETED or TOOL_ERROR event.")
) AS
WITH ToolStarts AS (
  SELECT
    trace_id,
    span_id,
    timestamp as start_timestamp,
    agent as agent_name,
    parent_span_id,
    JSON_VALUE(attributes, '$.root_agent_name') as root_agent_name,
    -- Extract tool name and args from Start event
    COALESCE(
        JSON_VALUE(content, '$.tool'),
        JSON_VALUE(attributes, '$.tool_name')
    ) as tool_name,
    JSON_QUERY(content, '$.args') as tool_args,
    attributes as start_attributes,
    user_id,
    session_id
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'TOOL_STARTING'
),
ToolEnds AS (
  SELECT
    trace_id,
    span_id,
    timestamp as end_timestamp,
    event_type,
    SAFE_CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64) as duration_ms,
    -- Extract result from End event
    JSON_QUERY(content, '$.result') as tool_result,
    error_message,
    status,
    -- Extract tool_name to help match errors logged on parent span
    COALESCE(
        JSON_VALUE(content, '$.tool'),
        JSON_VALUE(attributes, '$.tool_name')
    ) as tool_name
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type IN ('TOOL_COMPLETED', 'TOOL_ERROR')
)
SELECT
    S.start_timestamp as timestamp,
    S.root_agent_name,
    S.agent_name,

    S.tool_name,
    S.tool_args,
    E.tool_result,

    E.duration_ms,
    CASE
        WHEN E.error_message IS NULL AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 AND E.status IS NULL THEN 'Tool span PENDING for > 5 minutes (Timed Out)'
        ELSE E.error_message
    END as error_message,
      CASE
        WHEN E.event_type = 'TOOL_ERROR' THEN 'ERROR'
        WHEN E.status IS NOT NULL THEN E.status
        WHEN TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 THEN 'ERROR'
        ELSE 'PENDING'
    END as status,

    S.span_id,
    S.trace_id,
    S.parent_span_id,
    S.user_id,
    S.session_id,

    S.start_timestamp,
    E.end_timestamp,


FROM ToolStarts S
    LEFT JOIN ToolEnds E
ON S.trace_id = E.trace_id
    AND (
    -- Normal case: spans match (Completed or correctly logged Error)
    S.span_id = E.span_id
    OR
    -- "Parent Logged" Error case: Error logged on parent span
    -- This happens because on_tool_error_callback pops the span but doesn't override span_id in the log
    (E.event_type = 'TOOL_ERROR' AND S.parent_span_id = E.span_id AND S.tool_name = E.tool_name)
    );
