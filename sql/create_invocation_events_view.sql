/*
 * Invocation Events View
 * ----------------------
 * Aggregates information about Agent Invocations (runs).
 * Combines the lifecycle events (STARTING, COMPLETED) with the User Message
 * that triggered the invocation.
 *
 * Key Identifiers:
 * - invocation_id: The unique ID for this specific run/turn.
 * - session_id: The higher-level session ID (multi-turn conversation).
 */
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.invocation_events_view` AS
WITH InvocationStarts AS (
  SELECT
    invocation_id,
    session_id,
    trace_id,
    timestamp as start_timestamp,
    attributes as start_attributes,
    agent as agent_name,
    JSON_VALUE(attributes, '$.root_agent_name') as root_agent_name,
    user_id
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'INVOCATION_STARTING'
),
InvocationEnds AS (
  SELECT
    invocation_id,
    timestamp as end_timestamp,
    JSON_VALUE(attributes, '$.root_agent_name') as root_agent_name,
    status,
    error_message
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'INVOCATION_COMPLETED'
),
UserMessages AS (
  SELECT
    invocation_id,
    timestamp as message_timestamp,
    content as user_message,
    content_parts,
    JSON_VALUE(content, '$.text_summary') as content_text_summary
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'USER_MESSAGE_RECEIVED'
)
SELECT
  S.start_timestamp as timestamp,
  COALESCE(E.root_agent_name, S.root_agent_name, S.agent_name) as root_agent_name,
  S.agent_name,
  M.content_text_summary,
  -- Extract text from the first part of the generic content_parts array column
  M.content_parts[SAFE_OFFSET(0)].text as content_text,

  TIMESTAMP_DIFF(E.end_timestamp, S.start_timestamp, MILLISECOND) as duration_ms,
  CASE
    WHEN E.status IS NULL AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 THEN 'ERROR'
    ELSE COALESCE(E.status, 'PENDING')
  END as status,
  CASE
    WHEN E.status IS NULL AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 THEN 'Invocation PENDING for > 5 minutes (Timed Out)'
    ELSE E.error_message
  END as error_message,

  M.message_timestamp,
  S.start_timestamp,
  E.end_timestamp,

  S.invocation_id,
  S.session_id,
  S.trace_id,
  S.user_id

FROM InvocationStarts S
    LEFT JOIN InvocationEnds E
ON S.invocation_id = E.invocation_id
    LEFT JOIN UserMessages M
    ON S.invocation_id = M.invocation_id;
