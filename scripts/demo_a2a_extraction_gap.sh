#!/bin/bash
# demo_a2a_extraction_gap.sh
#
# Walks through ONE real A2A session to show exactly why the SDK
# fails to classify it, and how the fix works.
#
# Usage:  ./scripts/demo_a2a_extraction_gap.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../.env" 2>/dev/null || true

PROJECT="${PROJECT_ID:?PROJECT_ID not set}"
DATASET="${DATASET_ID:?DATASET_ID not set}"
TABLE="${TABLE_ID:?TABLE_ID not set}"
FQN="${PROJECT}.${DATASET}.${TABLE}"

echo ""
echo "================================================================"
echo "  A2A_INTERACTION Extraction Bug Demo"
echo "  Table: ${FQN}"
echo "================================================================"

# Pick one A2A session to trace through
A2A_SESSION=$(bq query --nouse_legacy_sql --format=csv --max_rows=1 \
  "SELECT session_id FROM \`${FQN}\` WHERE event_type = 'A2A_INTERACTION' LIMIT 1" \
  2>/dev/null | tail -1)

echo ""
echo "Using session: ${A2A_SESSION}"
echo ""


########################################################################
echo "================================================================"
echo "  STEP 1: What happened in this session?"
echo ""
echo "  Each row in BigQuery is an event. Let's list them in order"
echo "  to understand the conversation flow."
echo "================================================================"
echo ""

bq query --nouse_legacy_sql --format=pretty "
SELECT
  event_type,
  agent
FROM \`${FQN}\`
WHERE session_id = '${A2A_SESSION}'
ORDER BY timestamp
"

echo ""
echo "  EXPLANATION:"
echo "  - USER_MESSAGE_RECEIVED: the user asked a question"
echo "  - LLM_RESPONSE: the supervisor decided to call transfer_to_agent"
echo "  - TOOL_STARTING/COMPLETED: the transfer_to_agent tool ran"
echo "  - A2A_INTERACTION: the remote agent (pto_agent) responded"
echo "  - AGENT_COMPLETED: session finished"
echo ""
echo "  The SDK builds a transcript by extracting text from each event's"
echo "  'content' column, then sends that transcript to AI.GENERATE"
echo "  for classification."
echo ""


########################################################################
echo "================================================================"
echo "  STEP 2: What does the A2A_INTERACTION content look like?"
echo ""
echo "  Every event has a 'content' column (JSON). For most events"
echo "  the text is at \$.response or \$.text_summary."
echo "  Let's see what the A2A_INTERACTION content looks like."
echo "================================================================"
echo ""

# Write content to a temp file to avoid CSV parsing issues
TMPFILE=$(mktemp)
bq query --nouse_legacy_sql --format=json --max_rows=1 "
SELECT TO_JSON_STRING(content) AS cj
FROM \`${FQN}\`
WHERE session_id = '${A2A_SESSION}' AND event_type = 'A2A_INTERACTION'
LIMIT 1
" 2>/dev/null > "$TMPFILE"

python3 - "$TMPFILE" <<'PYEOF'
import sys, json

with open(sys.argv[1]) as f:
    rows = json.load(f)
content = json.loads(rows[0]["cj"])

print("  Top-level keys in the content JSON:")
for key in content.keys():
    val = content[key]
    if isinstance(val, str) and len(val) > 60:
        print(f"    {key}: \"{val[:57]}...\"")
    elif isinstance(val, list):
        print(f"    {key}: [ ... {len(val)} items ]")
    elif isinstance(val, dict):
        print(f"    {key}: {{ {', '.join(val.keys())} }}")
    else:
        print(f"    {key}: {json.dumps(val)}")

print()
print("  The response text is nested inside artifacts:")
print()
artifacts = content.get("artifacts", [])
if artifacts:
    parts = artifacts[0].get("parts", [])
    if parts:
        text = parts[0].get("text", "")
        print(f"    content.artifacts[0].parts[0].text =")
        print(f"      \"{text[:200]}...\"" if len(text) > 200 else f"      \"{text}\"")
print()
print("  But the SDK looks for these top-level keys (none exist):")
for key in ["text_summary", "response", "tool"]:
    print(f"    content.{key} = {json.dumps(content.get(key))}")
PYEOF

rm -f "$TMPFILE"

echo ""


########################################################################
echo "================================================================"
echo "  STEP 3: What does the SDK extract? (the bug)"
echo ""
echo "  The SDK uses this SQL to extract text from each event:"
echo ""
echo "    COALESCE("
echo "      JSON_VALUE(content, '\$.text_summary'),"
echo "      JSON_VALUE(content, '\$.response'),"
echo "      JSON_VALUE(content, '\$.tool'),"
echo "      ''"
echo "    )"
echo ""
echo "  Let's run this on every event in our session:"
echo "================================================================"
echo ""

bq query --nouse_legacy_sql --format=pretty "
SELECT
  event_type,
  agent,
  COALESCE(
    JSON_VALUE(content, '\$.text_summary'),
    JSON_VALUE(content, '\$.response'),
    JSON_VALUE(content, '\$.tool'),
    ''
  ) AS extracted_text
FROM \`${FQN}\`
WHERE session_id = '${A2A_SESSION}'
ORDER BY timestamp
"

echo ""
echo "  EXPLANATION:"
echo "  Look at the A2A_INTERACTION row -- extracted_text is EMPTY."
echo "  The user's question was extracted, but the agent's answer was not."
echo "  AI.GENERATE sees: question + no answer => cannot classify => NULL."
echo ""


########################################################################
echo "================================================================"
echo "  STEP 4: With the fix"
echo ""
echo "  We add ONE line to the COALESCE:"
echo ""
echo "    COALESCE("
echo "      JSON_VALUE(content, '\$.text_summary'),"
echo "      JSON_VALUE(content, '\$.response'),"
echo "      JSON_VALUE(content, '\$.artifacts[0].parts[0].text'),  -- NEW"
echo "      JSON_VALUE(content, '\$.tool'),"
echo "      ''"
echo "    )"
echo ""
echo "  Same query, with the fix applied:"
echo "================================================================"
echo ""

bq query --nouse_legacy_sql --format=pretty "
SELECT
  event_type,
  agent,
  COALESCE(
    JSON_VALUE(content, '\$.text_summary'),
    JSON_VALUE(content, '\$.response'),
    JSON_VALUE(content, '\$.artifacts[0].parts[0].text'),
    JSON_VALUE(content, '\$.tool'),
    ''
  ) AS extracted_text
FROM \`${FQN}\`
WHERE session_id = '${A2A_SESSION}'
ORDER BY timestamp
"

echo ""
echo "  EXPLANATION:"
echo "  Now the A2A_INTERACTION row has the remote agent's response."
echo "  AI.GENERATE sees: question + answer => can classify => success."
echo ""


########################################################################
echo "================================================================"
echo "  STEP 5: How many sessions does this affect?"
echo "================================================================"
echo ""

bq query --nouse_legacy_sql --format=pretty "
SELECT
  COUNT(DISTINCT session_id) AS total_sessions,
  COUNT(DISTINCT CASE
    WHEN session_id IN (
      SELECT DISTINCT session_id FROM \`${FQN}\`
      WHERE event_type = 'A2A_INTERACTION'
    ) THEN session_id
  END) AS a2a_sessions_affected
FROM \`${FQN}\`
"

echo ""
echo "  Every A2A session above is currently unclassifiable."
echo ""
echo "================================================================"
echo "  Fix: add \$.artifacts[0].parts[0].text to the COALESCE chain"
echo "  in categorical_evaluator.py (4 locations)"
echo "================================================================"
echo ""
