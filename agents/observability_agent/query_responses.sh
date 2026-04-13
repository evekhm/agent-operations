#!/bin/bash
# Query user questions and agent responses from BigQuery
#
# Usage: bash query_responses.sh [LIMIT]
#   LIMIT: number of most recent sessions to return (default: 100)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$SCRIPT_DIR/../../.env"

if [ -f "$ENV_PATH" ]; then
    source "$ENV_PATH"
else
    echo "ERROR: .env not found at $ENV_PATH"
    exit 1
fi

LIMIT="${1:-100}"

echo "Querying last ${LIMIT} responses..."
echo "Project: ${PROJECT_ID}, Dataset: ${DATASET_ID}, Table: ${TABLE_ID}"
echo ""

bq query --use_legacy_sql=false --format=prettyjson --max_rows=${LIMIT} "
WITH
user_msgs AS (
  SELECT session_id,
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
agent_responses AS (
  SELECT session_id,
         agent,
         JSON_VALUE(content, '\$.response') AS response,
         timestamp AS resp_time,
         ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp DESC) AS rn
  FROM \`${PROJECT_ID}.${DATASET_ID}.${TABLE_ID}\`
  WHERE event_type = 'LLM_RESPONSE'
    AND JSON_VALUE(content, '\$.response') IS NOT NULL
    AND JSON_VALUE(content, '\$.response') NOT LIKE 'call:%'
)
SELECT
  u.session_id,
  FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', u.ask_time) AS time,
  SUBSTR(u.question, 0, 120) AS question,
  COALESCE(a.agent, 'no_response') AS answered_by,
  SUBSTR(a.response, 0, 300) AS response,
  TIMESTAMP_DIFF(a.resp_time, u.ask_time, SECOND) AS latency_s
FROM recent_users u
LEFT JOIN agent_responses a ON u.session_id = a.session_id AND a.rn = 1
ORDER BY u.ask_time DESC
"
