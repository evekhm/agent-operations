#!/bin/bash
# Query user questions, agent responses, and AI quality evaluation from BigQuery
# Handles both local sub-agents and remote A2A agents (which log under separate sessions)
#
# Usage: bash query_responses.sh [LIMIT] [--no-eval]
#   LIMIT:     number of most recent sessions to return (default: 100)
#   --no-eval: skip AI evaluation (faster, cheaper)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$SCRIPT_DIR/../../.env"

if [ -f "$ENV_PATH" ]; then
    source "$ENV_PATH"
else
    echo "ERROR: .env not found at $ENV_PATH"
    exit 1
fi

LIMIT="${1:-100}"
SKIP_EVAL=false

for arg in "$@"; do
    case "$arg" in
        --no-eval) SKIP_EVAL=true ;;
        [0-9]*) LIMIT="$arg" ;;
    esac
done

CONNECTION_ID="${CONNECTION_ID:-bqml_connection}"
EVAL_MODEL="${EVAL_MODEL_ID:-gemini-2.5-flash}"
FULL_CONNECTION="${PROJECT_ID}.${DATASET_LOCATION}.${CONNECTION_ID}"

if [ "$SKIP_EVAL" = true ]; then
    echo "Querying last ${LIMIT} responses (no evaluation)..."
else
    echo "Querying last ${LIMIT} responses with AI evaluation..."
    echo "Model: ${EVAL_MODEL}, Connection: ${FULL_CONNECTION}"
fi
echo "Project: ${PROJECT_ID}, Dataset: ${DATASET_ID}, Table: ${TABLE_ID}"
echo ""

# Build the eval column: either AI.GENERATE or a placeholder
if [ "$SKIP_EVAL" = true ]; then
    EVAL_SELECT="NULL AS evaluation"
else
    EVAL_SELECT="
    CASE
      WHEN COALESCE(lr.response, rr.response) IS NULL THEN 'NO_RESPONSE'
      ELSE (
        SELECT AI.GENERATE(
          CONCAT(
            'Evaluate this agent interaction in ONE line. Rate as GOOD, PARTIAL, or BAD. ',
            'GOOD = directly answers the question with specific info. ',
            'PARTIAL = related but incomplete or not exactly what was asked. ',
            'BAD = cannot help, no data, generic filler, or wrong topic. ',
            'Format: RATING: explanation. ',
            'Question: ', COALESCE(u.question, ''), ' ',
            'Response: ', SUBSTR(COALESCE(lr.response, rr.response, ''), 0, 500)
          ),
          connection_id => '${FULL_CONNECTION}',
          endpoint => '${EVAL_MODEL}'
        ).result
      )
    END AS evaluation"
fi

bq query --use_legacy_sql=false --format=prettyjson --max_rows=${LIMIT} "
WITH
-- 1. Most recent user questions
user_msgs AS (
  SELECT session_id, trace_id,
         JSON_VALUE(content, '\$.text_summary') AS question,
         timestamp AS ask_time,
         ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp ASC) AS rn
  FROM \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\`
  WHERE event_type = 'USER_MESSAGE_RECEIVED'
),
recent_users AS (
  SELECT * FROM user_msgs
  WHERE rn = 1
  ORDER BY ask_time DESC
  LIMIT ${LIMIT}
),
-- 2. Local sub-agent responses (same session_id as supervisor)
local_responses AS (
  SELECT session_id,
         agent,
         JSON_VALUE(content, '\$.response') AS response,
         timestamp AS resp_time,
         ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp DESC) AS rn
  FROM \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\`
  WHERE event_type = 'LLM_RESPONSE'
    AND JSON_VALUE(content, '\$.response') IS NOT NULL
    AND JSON_VALUE(content, '\$.response') NOT LIKE 'call:%'
),
-- 3. WORKAROUND for A2A trace correlation gap:
--    Remote A2A agents (e.g. pto_agent on Cloud Run) log their LLM events
--    under a DIFFERENT session_id. The supervisor only logs AGENT_STARTING
--    and AGENT_COMPLETED with content=null for the remote agent.
--    We use the supervisor's AGENT time window to find the remote agent's
--    own response by matching agent name + timestamp range.
remote_agent_windows AS (
  SELECT s.session_id,
         s.agent AS remote_agent,
         s.timestamp AS agent_start,
         c.timestamp AS agent_end
  FROM \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\` s
  JOIN \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\` c
    ON s.session_id = c.session_id
    AND s.agent = c.agent
    AND s.span_id = c.span_id
  WHERE s.event_type = 'AGENT_STARTING'
    AND c.event_type = 'AGENT_COMPLETED'
    AND s.agent != 'knowledge_supervisor'
),
-- 4. Remote agent's OWN response (different session, matched by time window)
remote_responses AS (
  SELECT r.session_id AS remote_session_id,
         r.agent,
         JSON_VALUE(r.content, '\$.response') AS response,
         r.timestamp AS resp_time,
         w.session_id AS parent_session_id,
         ROW_NUMBER() OVER (PARTITION BY w.session_id ORDER BY r.timestamp DESC) AS rn
  FROM \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\` r
  JOIN remote_agent_windows w
    ON r.agent = w.remote_agent
    AND r.timestamp BETWEEN w.agent_start AND w.agent_end
    AND r.session_id != w.session_id
  WHERE r.event_type = 'LLM_RESPONSE'
    AND JSON_VALUE(r.content, '\$.response') IS NOT NULL
    AND JSON_VALUE(r.content, '\$.response') NOT LIKE 'call:%'
)
SELECT
  u.session_id,
  FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', u.ask_time) AS time,
  SUBSTR(u.question, 0, 120) AS question,
  COALESCE(lr.agent, rr.agent, 'no_response') AS answered_by,
  SUBSTR(COALESCE(lr.response, rr.response), 0, 300) AS response,
  COALESCE(
    TIMESTAMP_DIFF(lr.resp_time, u.ask_time, SECOND),
    TIMESTAMP_DIFF(rr.resp_time, u.ask_time, SECOND)
  ) AS latency_s,
  ${EVAL_SELECT}
FROM recent_users u
LEFT JOIN local_responses lr ON u.session_id = lr.session_id AND lr.rn = 1
LEFT JOIN remote_responses rr ON u.session_id = rr.parent_session_id AND rr.rn = 1 AND lr.response IS NULL
ORDER BY u.ask_time DESC
"
