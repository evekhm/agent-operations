/*
 * Agent Events View
 * -----------------
 * Tracks the execution lifecycle of agents (STARTING, COMPLETED).
 * Provides insights into agent latency, instructions, and overall flow.
 * Joins AGENT_STARTING with AGENT_COMPLETED via span_id.
 *
 * Status Note:
 * - 'PENDING': Assigned when an AGENT_STARTING event has no corresponding
 *   AGENT_COMPLETED event. This indicates the agent is either still running
 *   or crashed/terminated unexpectedly.
 */
CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.agent_events_view` AS
WITH AgentStarts AS (
  SELECT
    trace_id,
    span_id,
    timestamp as start_timestamp,
    agent as agent_name,
    parent_span_id,
    JSON_VALUE(attributes, '$.root_agent_name') as root_agent_name,
    content as instruction,
    attributes as start_attributes,
    user_id,
    session_id
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type = 'AGENT_STARTING'
),
AgentEnds AS (
  SELECT
    trace_id,
    span_id,
    timestamp as end_timestamp,
    event_type,
    SAFE_CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64) as duration_ms,
    status,
    error_message
  FROM `{project_id}.{dataset_id}.{table_id}`
  WHERE event_type IN ('AGENT_COMPLETED')
)
SELECT
    S.start_timestamp as timestamp,
    S.root_agent_name,
    S.agent_name,

    S.instruction,

    E.duration_ms,
    CASE
      WHEN E.status IS NULL AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 THEN 'ERROR'
      ELSE COALESCE(E.status, 'PENDING')
    END as status,
    CASE
      WHEN E.status IS NULL AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), S.start_timestamp, MINUTE) > 5 THEN 'Agent span PENDING for > 5 minutes (Timed Out)'
      ELSE E.error_message
    END as error_message,

    S.span_id,
    S.trace_id,
    S.parent_span_id,
    S.user_id,
    S.session_id,

    S.start_timestamp,
    E.end_timestamp


FROM AgentStarts S
    LEFT JOIN AgentEnds E
ON S.trace_id = E.trace_id
    AND S.span_id = E.span_id;
