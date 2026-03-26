import os
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import pandas as pd

from google.cloud import geminidataanalytics
from config import (PROJECT_ID, DATASET_ID, TABLE_ID, AGENT_EVENTS_VIEW, CA_LOCATION,
                    INVOCATION_EVENTS_VIEW, TOOL_EVENTS_VIEW, LLM_EVENTS_VIEW, DATASET_LOCATION)
# Import Libraries & Initialize Plugin, Tools, Models and Agent
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.google_llm import Gemini
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryAgentAnalyticsPlugin
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.tool_context import ToolContext

# Two clients: one manages Data Agents, the other handles conversations
data_agent_client = geminidataanalytics.DataAgentServiceClient()
data_chat_client = geminidataanalytics.DataChatServiceClient()

import uuid as _uuid
_run_id = _uuid.uuid4().hex[:8]
CA_CONVERSATION_ID=f"agent_ops_conv_{_run_id}"
CA_AGENT_ID=f"ca_agent_ops_{_run_id}"
# --- Initialize the Plugin ---
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,  # project_id is required input from user
    dataset_id=DATASET_ID,  # dataset_id is required input from user
    table_id=TABLE_ID,
    location=DATASET_LOCATION,
    # Optional: defaults to "agent_events". The plugin automatically creates
    # this table if it doesn't exist.
)
print(f"BigQueryAgentAnalyticsPlugin initialized, streaming data to {PROJECT_ID}:{DATASET_ID}.{TABLE_ID} in {DATASET_LOCATION}")

# --- Initialize Tools & Model ---
credentials, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
bigquery_toolset = BigQueryToolset(
    credentials_config=BigQueryCredentialsConfig(credentials=credentials)
)

llm = Gemini(
    model="gemini-2.5-flash",
)

def set_state(key: str, value: str, tool_context: ToolContext) -> str:
    """Sets a key-value pair in the session state."""
    tool_context.state[key] = value
    return f"Set state {key} to {value}"


root_agent = Agent(
    model=llm,
    name="ca_agent",
    instruction=(
        f"You are the Agent Operations Observability Analyst — a specialized data analyst "
        f"that helps engineers understand the behavior, performance, errors, and usage patterns "
        f"of multi-agent AI systems built with Google's Agent Development Kit (ADK).\n\n"
        f"You operate on telemetry data stored in BigQuery:\n"
        f"  - Project: {PROJECT_ID}\n"
        f"  - Dataset: {DATASET_ID}\n"
        f"  - Primary base table: {TABLE_ID}\n\n"
        f"You have four pre-built semantic views optimized for analysis:\n"
        f"  1. `{AGENT_EVENTS_VIEW}` — Agent execution lifecycle (start, end, latency, errors per span).\n"
        f"  2. `{INVOCATION_EVENTS_VIEW}` — End-to-end invocation (user turn) metrics including user message.\n"
        f"  3. `{LLM_EVENTS_VIEW}` — LLM call details: tokens, latency, model version, full request/response.\n"
        f"  4. `{TOOL_EVENTS_VIEW}` — Tool execution details: tool name, args, results, latency, errors.\n\n"
        f"Always prefer these views over querying the raw `{TABLE_ID}` table directly. "
        f"Use the raw table only for event-level analysis such as tracing a specific session, "
        f"multimodal content inspection (content_parts), HITL events, or state deltas.\n\n"
        f"You can answer questions such as:\n"
        f"  - What is the P95 latency for each agent or model?\n"
        f"  - Which agents or tools have the highest error rates?\n"
        f"  - Are there hallucination loops (runaway token generation)?\n"
        f"  - What is the token usage breakdown by agent, model, or root agent?\n"
        f"  - What errors occurred in the last 24 hours?\n"
        f"  - Which invocations are slowest and why?\n"
        f"  - Can you analyze a specific trace or session end-to-end?\n\n"
        f"When asked 'who are you', 'what do you do', or 'what data do you have access to', "
        f"introduce yourself with the above role, explain the data sources, and list the kinds of "
        f"questions you can answer.\n\n"
        f"Always use project `{PROJECT_ID}` for billing. "
        f"Use CURRENT_TIMESTAMP() for current time comparisons in queries."
    ),
    tools=[bigquery_toolset, set_state],
    generate_content_config={
        "temperature": 0.5,
        "top_p": 0.9,
    },
)

# --- Create the App ---
app = App(
    name="ca_agent",
    root_agent=root_agent,
    plugins=[bq_logging_plugin], # Register the plugin here
)
print(f"ca_agent initialized for project {PROJECT_ID}, dataset {DATASET_ID}")

def ca_ask(question):
    """Send a natural language question to the CA Data Agent."""
    messages = [
        geminidataanalytics.Message(
            user_message=geminidataanalytics.UserMessage(text=question)
        )
    ]
    request = geminidataanalytics.ChatRequest(
        parent=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}",
        messages=messages,
        conversation_reference=geminidataanalytics.ConversationReference(
            conversation=data_chat_client.conversation_path(
                PROJECT_ID, CA_LOCATION, CA_CONVERSATION_ID
            ),
            data_agent_context=geminidataanalytics.DataAgentContext(
                data_agent=data_agent_client.data_agent_path(
                    PROJECT_ID, CA_LOCATION, CA_AGENT_ID
                )
            ),
        ),
    )
    return list(data_chat_client.chat(request=request, timeout=300))


def display_ca_response(responses):
    """Parse and display CA streaming responses: text, SQL, data tables."""
    for resp in responses:
        m = resp.system_message
        if "text" in m and m.text.text_type != geminidataanalytics.TextMessage.TextType.THOUGHT:
            print("\n".join(m.text.parts))
        elif "data" in m:
            if "generated_sql" in m.data:
                print(f"\n--- Generated SQL ---\n{m.data.generated_sql}")
            elif "result" in m.data:
                # Convert to pandas DataFrame and display
                fields = [f.name for f in m.data.result.schema.fields]
                rows = [{f: row[f] for f in fields} for row in m.data.result.data]
                print(pd.DataFrame(rows).to_markdown(index=False))


# Define the data source: the BQ AA Plugin's event log table
bq_references = []

# --- Reference for the Table to Analyze ---
table_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id=TABLE_ID,
    schema=geminidataanalytics.Schema(
        description='The events table uses a flexible schema. Use this table for detailed, event-level analysis.',
        fields=[
            geminidataanalytics.Field(name='timestamp', description='UTC timestamp of event creation. Acts as the primary ordering key and the daily partitioning key. Precision is microsecond.'),
            geminidataanalytics.Field(name='event_type', description='The canonical event category. Standard values include LLM_REQUEST, LLM_RESPONSE, LLM_ERROR, TOOL_STARTING, TOOL_COMPLETED, TOOL_ERROR, AGENT_STARTING, AGENT_COMPLETED, STATE_DELTA, INVOCATION_STARTING, INVOCATION_COMPLETED, USER_MESSAGE_RECEIVED, and HITL events.'),
            geminidataanalytics.Field(name='agent', description='The name of the agent responsible for this event.'),
            geminidataanalytics.Field(name='session_id', description='A persistent identifier for the entire conversation thread. Stays constant across multiple turns and sub-agent calls.'),
            geminidataanalytics.Field(name='invocation_id', description='The unique identifier for a single execution turn or request cycle. Corresponds to trace_id in many contexts.'),
            geminidataanalytics.Field(name='user_id', description='The identifier of the user (human or system) initiating the session.'),
            geminidataanalytics.Field(name='trace_id', description='The OpenTelemetry Trace ID (32-char hex). Links all operations within a single distributed request lifecycle.'),
            geminidataanalytics.Field(name='span_id', description='The OpenTelemetry Span ID (16-char hex). Uniquely identifies this specific atomic operation.'),
            geminidataanalytics.Field(name='parent_span_id', description='The Span ID of the immediate caller. Used to reconstruct the parent-child execution tree (DAG).'),
            geminidataanalytics.Field(name='content', description='The primary event payload. Structure is polymorphic based on event_type. Store as a JSON string.'),
            geminidataanalytics.Field(name='attributes', description='Metadata/Enrichment (usage stats, model info, tool provenance, custom tags). Store as a JSON string.'),
            geminidataanalytics.Field(name='latency_ms', description='Performance metrics. Standard keys are total_ms (wall-clock duration) and time_to_first_token_ms (streaming latency). Store as a JSON string.'),
            geminidataanalytics.Field(name='status', description='High-level outcome. Values: OK (success) or ERROR (failure).'),
            geminidataanalytics.Field(name='error_message', description='Human-readable exception message or stack trace fragment. Populated only when status is ERROR.'),
            geminidataanalytics.Field(name='is_truncated', description='true if content or attributes exceeded the BigQuery cell size limit (default 10MB) and were partially dropped.'),
            geminidataanalytics.Field(name='content_parts', description='Array of multi-modal segments (Text, Image, Blob). Used when content cannot be serialized as simple JSON (e.g., large binaries or GCS refs).'),
        ]
    )
)
bq_references.append(table_ref)

# --- Reference for v_agent_completed ---
v_agent_completed_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_agent_completed',
    schema=geminidataanalytics.Schema(
        description='Schema for v_agent_completed',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='total_ms', description=''),
        ]
    )
)
bq_references.append(v_agent_completed_ref)

# --- Reference for v_agent_starting ---
v_agent_starting_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_agent_starting',
    schema=geminidataanalytics.Schema(
        description='Schema for v_agent_starting',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='agent_instruction', description=''),
        ]
    )
)
bq_references.append(v_agent_starting_ref)

# --- Reference for v_hitl_confirmation_request ---
v_hitl_confirmation_request_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_hitl_confirmation_request',
    schema=geminidataanalytics.Schema(
        description='Schema for v_hitl_confirmation_request',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='tool_name', description=''),
            geminidataanalytics.Field(name='tool_args', description=''),
        ]
    )
)
bq_references.append(v_hitl_confirmation_request_ref)

# --- Reference for v_hitl_credential_request ---
v_hitl_credential_request_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_hitl_credential_request',
    schema=geminidataanalytics.Schema(
        description='Schema for v_hitl_credential_request',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='tool_name', description=''),
            geminidataanalytics.Field(name='tool_args', description=''),
        ]
    )
)
bq_references.append(v_hitl_credential_request_ref)

# --- Reference for v_hitl_input_request ---
v_hitl_input_request_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_hitl_input_request',
    schema=geminidataanalytics.Schema(
        description='Schema for v_hitl_input_request',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='tool_name', description=''),
            geminidataanalytics.Field(name='tool_args', description=''),
        ]
    )
)
bq_references.append(v_hitl_input_request_ref)

# --- Reference for v_invocation_completed ---
v_invocation_completed_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_invocation_completed',
    schema=geminidataanalytics.Schema(
        description='Schema for v_invocation_completed',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
        ]
    )
)
bq_references.append(v_invocation_completed_ref)

# --- Reference for v_invocation_starting ---
v_invocation_starting_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_invocation_starting',
    schema=geminidataanalytics.Schema(
        description='Schema for v_invocation_starting',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
        ]
    )
)
bq_references.append(v_invocation_starting_ref)

# --- Reference for v_llm_error ---
v_llm_error_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_llm_error',
    schema=geminidataanalytics.Schema(
        description='Schema for v_llm_error',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='total_ms', description=''),
        ]
    )
)
bq_references.append(v_llm_error_ref)

# --- Reference for v_llm_request ---
v_llm_request_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_llm_request',
    schema=geminidataanalytics.Schema(
        description='Schema for v_llm_request',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='model', description=''),
            geminidataanalytics.Field(name='request_content', description=''),
            geminidataanalytics.Field(name='llm_config', description=''),
            geminidataanalytics.Field(name='tools', description=''),
        ]
    )
)
bq_references.append(v_llm_request_ref)

# --- Reference for v_llm_response ---
v_llm_response_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_llm_response',
    schema=geminidataanalytics.Schema(
        description='Schema for v_llm_response',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='response', description=''),
            geminidataanalytics.Field(name='usage_prompt_tokens', description=''),
            geminidataanalytics.Field(name='usage_completion_tokens', description=''),
            geminidataanalytics.Field(name='usage_total_tokens', description=''),
            geminidataanalytics.Field(name='total_ms', description=''),
            geminidataanalytics.Field(name='ttft_ms', description=''),
            geminidataanalytics.Field(name='model_version', description=''),
            geminidataanalytics.Field(name='usage_metadata', description=''),
        ]
    )
)
bq_references.append(v_llm_response_ref)

# --- Reference for v_state_delta ---
v_state_delta_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='v_state_delta',
    schema=geminidataanalytics.Schema(
        description='Schema for v_state_delta',
        fields=[
            geminidataanalytics.Field(name='timestamp', description=''),
            geminidataanalytics.Field(name='event_type', description=''),
            geminidataanalytics.Field(name='agent', description=''),
            geminidataanalytics.Field(name='session_id', description=''),
            geminidataanalytics.Field(name='invocation_id', description=''),
            geminidataanalytics.Field(name='user_id', description=''),
            geminidataanalytics.Field(name='trace_id', description=''),
            geminidataanalytics.Field(name='span_id', description=''),
            geminidataanalytics.Field(name='parent_span_id', description=''),
            geminidataanalytics.Field(name='status', description=''),
            geminidataanalytics.Field(name='error_message', description=''),
            geminidataanalytics.Field(name='is_truncated', description=''),
            geminidataanalytics.Field(name='state_delta', description=''),
        ]
    )
)
bq_references.append(v_state_delta_ref)

# --- Reference for agent_events_view ---
agent_events_view_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='agent_events_view',
    schema=geminidataanalytics.Schema(
        description='View for agent execution lifecycle events (STARTING, COMPLETED). Serves as a semantic layer for analyzing latency and success rates of agent actions.',
        fields=[
            geminidataanalytics.Field(name='timestamp', description='The timestamp of the AGENT_STARTING event. Used as the primary time-series anchor.'),
            geminidataanalytics.Field(name='root_agent_name', description='The name of the root agent that initiated the invocation.'),
            geminidataanalytics.Field(name='agent_name', description='The name of the agent executing this span.'),
            geminidataanalytics.Field(name='instruction', description='The instruction or input provided to the agent.'),
            geminidataanalytics.Field(name='duration_ms', description='The total time in milliseconds from AGENT_STARTING to AGENT_COMPLETED.'),
            geminidataanalytics.Field(name='status', description='The execution status. OK on success, ERROR on failure, or PENDING if the agent is still running or crashed.'),
            geminidataanalytics.Field(name='error_message', description='The exception message if the agent encountered an error.'),
            geminidataanalytics.Field(name='span_id', description='The OpenTelemetry span_id identifying this specific agent execution.'),
            geminidataanalytics.Field(name='trace_id', description='The OpenTelemetry trace_id tying this execution back to the root invocation.'),
            geminidataanalytics.Field(name='parent_span_id', description='The span_id of the operation that called this agent.'),
            geminidataanalytics.Field(name='user_id', description='The ID of the user who initiated the run.'),
            geminidataanalytics.Field(name='session_id', description='The ID of the multi-turn session.'),
            geminidataanalytics.Field(name='start_timestamp', description='The exact timestamp of the AGENT_STARTING event.'),
            geminidataanalytics.Field(name='end_timestamp', description='The exact timestamp of the AGENT_COMPLETED event.'),
        ]
    )
)

# --- Reference for invocation_events_view ---
invocation_events_view_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='invocation_events_view',
    schema=geminidataanalytics.Schema(
        description='View for Agent Invocations (runs). Aggregates information about a single turn or execution within a session.',
        fields=[
            geminidataanalytics.Field(name='timestamp', description='The start timestamp of the invocation. Used as the primary time-series anchor.'),
            geminidataanalytics.Field(name='root_agent_name', description='The designated root agent for this invocation.'),
            geminidataanalytics.Field(name='agent_name', description='The name of the agent that started the invocation.'),
            geminidataanalytics.Field(name='content_text_summary', description='A summary of the user input message that triggered the invocation.'),
            geminidataanalytics.Field(name='content_text', description='The primary text of the user input message.'),
            geminidataanalytics.Field(name='duration_ms', description='The total time in milliseconds from INVOCATION_STARTING to INVOCATION_COMPLETED.'),
            geminidataanalytics.Field(name='status', description='The execution status. OK on success, ERROR on failure, or PENDING if the run is still active or crashed.'),
            geminidataanalytics.Field(name='error_message', description='The exception message if the invocation encountered an error.'),
            geminidataanalytics.Field(name='message_timestamp', description='The timestamp when the user message was received.'),
            geminidataanalytics.Field(name='start_timestamp', description='The exact timestamp of the INVOCATION_STARTING event.'),
            geminidataanalytics.Field(name='end_timestamp', description='The exact timestamp of the INVOCATION_COMPLETED event.'),
            geminidataanalytics.Field(name='invocation_id', description='A unique ID for this specific run/turn.'),
            geminidataanalytics.Field(name='session_id', description='The ID of the multi-turn conversation session.'),
            geminidataanalytics.Field(name='trace_id', description='The OpenTelemetry trace_id.'),
            geminidataanalytics.Field(name='span_id', description='The OpenTelemetry span_id.'),
            geminidataanalytics.Field(name='user_id', description='The ID of the user who initiated the run.'),
        ]
    )
)

# --- Reference for llm_events_view ---
llm_events_view_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='llm_events_view',
    schema=geminidataanalytics.Schema(
        description='View for LLM interactions. Isolates requests and responses from the event stream.',
        fields=[
            geminidataanalytics.Field(name='timestamp', description='The timestamp of the LLM_REQUEST event. Used as the primary time-series anchor.'),
            geminidataanalytics.Field(name='root_agent_name', description='The name of the root agent that initiated the invocation.'),
            geminidataanalytics.Field(name='agent_name', description='The name of the agent that made the LLM call.'),
            geminidataanalytics.Field(name='llm_config', description='JSON representation of the LLM configuration.'),
            geminidataanalytics.Field(name='usage_metadata', description='JSON representation of token usage metrics.'),
            geminidataanalytics.Field(name='model_name', description='The model name (specific version from response preferred).'),
            geminidataanalytics.Field(name='requested_model', description='The requested model.'),
            geminidataanalytics.Field(name='response_model', description='The response model.'),
            geminidataanalytics.Field(name='duration_ms', description='The total time in milliseconds.'),
            geminidataanalytics.Field(name='time_to_first_token_ms', description='The time to first token.'),
            geminidataanalytics.Field(name='status', description='The outcome of the LLM call.'),
            geminidataanalytics.Field(name='error_message', description='The exception message.'),
            geminidataanalytics.Field(name='prompt_token_count', description='The number of tokens in the input prompt.'),
            geminidataanalytics.Field(name='candidates_token_count', description='The number of tokens generated.'),
            geminidataanalytics.Field(name='total_token_count', description='The total number of tokens.'),
            geminidataanalytics.Field(name='thoughts_token_count', description='The number of tokens used for thinking/reasoning.'),
            geminidataanalytics.Field(name='full_request', description='The raw JSON content of the LLM request.'),
            geminidataanalytics.Field(name='full_response', description='The raw JSON content of the LLM response.'),
            geminidataanalytics.Field(name='request_text', description='The extracted text portion of the user prompt.'),
            geminidataanalytics.Field(name='response_text', description='The extracted text portion of the model response.'),
            geminidataanalytics.Field(name='span_id', description='The OpenTelemetry span_id.'),
            geminidataanalytics.Field(name='trace_id', description='The OpenTelemetry trace_id.'),
            geminidataanalytics.Field(name='parent_span_id', description='The span_id of the operation that made this LLM call.'),
            geminidataanalytics.Field(name='user_id', description='The ID of the user.'),
            geminidataanalytics.Field(name='session_id', description='The ID of the multi-turn session.'),
            geminidataanalytics.Field(name='start_timestamp', description='The exact timestamp of the LLM_REQUEST event.'),
            geminidataanalytics.Field(name='end_timestamp', description='The exact timestamp of the LLM_RESPONSE event.'),
        ]
    )
)

# --- Reference for tool_events_view ---
tool_events_view_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id='tool_events_view',
    schema=geminidataanalytics.Schema(
        description='View for tool execution events (STARTING, COMPLETED, ERROR).',
        fields=[
            geminidataanalytics.Field(name='timestamp', description='The timestamp of the TOOL_STARTING event. Used as the primary time-series anchor.'),
            geminidataanalytics.Field(name='root_agent_name', description='The name of the root agent that initiated the invocation.'),
            geminidataanalytics.Field(name='agent_name', description='The name of the agent executing the tool.'),
            geminidataanalytics.Field(name='tool_name', description='The name of the executed tool.'),
            geminidataanalytics.Field(name='tool_args', description='JSON representation of arguments passed to the tool.'),
            geminidataanalytics.Field(name='tool_result', description='JSON representation of tool result.'),
            geminidataanalytics.Field(name='duration_ms', description='The total time in milliseconds.'),
            geminidataanalytics.Field(name='error_message', description='The exception message.'),
            geminidataanalytics.Field(name='status', description='The execution status.'),
            geminidataanalytics.Field(name='span_id', description='The OpenTelemetry span_id.'),
            geminidataanalytics.Field(name='trace_id', description='The OpenTelemetry trace_id.'),
            geminidataanalytics.Field(name='parent_span_id', description='The span_id of the operation that called the tool.'),
            geminidataanalytics.Field(name='user_id', description='The ID of the user.'),
            geminidataanalytics.Field(name='session_id', description='The ID of the multi-turn session.'),
            geminidataanalytics.Field(name='start_timestamp', description='The exact timestamp of the TOOL_STARTING event.'),
            geminidataanalytics.Field(name='end_timestamp', description='The exact timestamp of the TOOL_COMPLETED event.'),
        ]
    )
)

bq_references = [agent_events_view_ref, invocation_events_view_ref, llm_events_view_ref, tool_events_view_ref]



datasource_references = geminidataanalytics.DatasourceReferences(
    bq=geminidataanalytics.BigQueryTableReferences(table_references=bq_references)
)

example_queries = [
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by root agent",
        sql_query=f"""
SELECT
    agent_name,
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
FROM
    `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
WHERE
    T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
    AND agent_name != root_agent_name
GROUP BY 1
ORDER BY avg_ms DESC, total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by invocation",
        sql_query=f"""
SELECT
    root_agent_name,
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
FROM
    `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE
    T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
GROUP BY 1
ORDER BY avg_ms DESC, total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by tool",
        sql_query=f"""
SELECT
    tool_name,
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
FROM
    `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW}` AS T
WHERE
    T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
    AND tool_name != 'transfer_to_agent'
GROUP BY 1
ORDER BY avg_ms DESC, total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze latency grouped by LLM",
        sql_query=f"""
SELECT
    model_name,
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
    MAX(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as max_ms,
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
    APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens,
    CORR(duration_ms, prompt_token_count) as corr_latency_input,
    CORR(duration_ms, candidates_token_count) as corr_latency_output,
    CORR(duration_ms, total_token_count) as corr_latency_total
FROM
    `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE
    T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
GROUP BY 1
ORDER BY avg_ms DESC, total_count DESC
""",
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
        sql_query=f"""
SELECT
    agent_name,
    model_name,
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
    MAX(IF(status != 'ERROR' AND status != 'PENDING', duration_ms, NULL)) as max_ms,
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
    APPROX_QUANTILES(total_token_count, 100)[OFFSET(95)] as p95_total_tokens,
    CORR(duration_ms, prompt_token_count) as corr_latency_input,
    CORR(duration_ms, candidates_token_count) as corr_latency_output,
    CORR(duration_ms, total_token_count) as corr_latency_total
FROM
    `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE
    T.timestamp BETWEEN '2000-01-01 00:00:00' AND '2026-03-25 03:39:13'
GROUP BY 1, 2
ORDER BY avg_ms DESC, total_count DESC
""",
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
        natural_language_question="Categorize invocation errors by type",
        sql_query=f"""
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
    END AS category,
    COUNT(*) AS total_count
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY category
ORDER BY total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by root agent",
        sql_query=f"""
SELECT
    root_agent_name,
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
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY 1
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by sub-agent",
        sql_query=f"""
SELECT
    agent_name,
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
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND agent_name != root_agent_name
GROUP BY 1
""",
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
        natural_language_question="Categorize tool errors by type",
        sql_query=f"""
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
    END AS category,
    COUNT(*) AS total_count
FROM `{PROJECT_ID}.{DATASET_ID}.{TOOL_EVENTS_VIEW}` AS T
WHERE T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
    AND tool_name NOT IN ('transfer_to_agent')
GROUP BY category
ORDER BY total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Categorize sub-agent errors by type",
        sql_query=f"""
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
    END AS category,
    COUNT(*) AS total_count
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
WHERE T.agent_name != T.root_agent_name
    AND T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY category
ORDER BY total_count DESC
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show token usage statistics by agent and model",
        sql_query=f"""
SELECT
    agent_name,
    model_name,
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
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY 1, 2
""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Categorize LLM errors by type",
        sql_query=f"""
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
    END AS category,
    COUNT(*) AS total_count
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}` AS T
WHERE T.status = 'ERROR'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY category
ORDER BY total_count DESC
""",
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

published_context = geminidataanalytics.Context(
    system_instruction=(
        f"You are the Agent Operations Observability Analyst — a specialized data analyst "
        f"that helps engineers understand the behavior, performance, errors, and usage patterns "
        f"of multi-agent AI systems built with Google's Agent Development Kit (ADK).\n\n"
        f"You operate on telemetry data stored in BigQuery:\n"
        f"  - Project: {PROJECT_ID}\n"
        f"  - Dataset: {DATASET_ID}\n"
        f"  - Primary base table: {TABLE_ID}\n\n"
        f"You have four pre-built semantic views optimized for analysis:\n"
        f"  1. `agent_events_view` — Agent execution lifecycle (start, end, latency, errors per span).\n"
        f"  2. `invocation_events_view` — End-to-end invocation (user turn) metrics including user message.\n"
        f"  3. `llm_events_view` — LLM call details: tokens, latency, model version, full request/response.\n"
        f"  4. `tool_events_view` — Tool execution details: tool name, args, results, latency, errors.\n\n"
        f"Always prefer these views for analysis. Use the raw `{TABLE_ID}` table only for "
        f"event-level tracing, multimodal content inspection, HITL events, or state deltas.\n\n"
        f"You can answer questions such as:\n"
        f"  - What is the P95 latency for each agent or model?\n"
        f"  - Which agents or tools have the highest error rates?\n"
        f"  - Are there hallucination loops (runaway token generation)?\n"
        f"  - What is the token usage breakdown by agent, model, or root agent?\n"
        f"  - What errors occurred in the last 24 hours?\n"
        f"  - Which invocations are slowest and why?\n\n"
        f"When asked 'who are you', 'what data do you have access to', or 'what can you do', "
        f"introduce yourself with the above role, explain the data sources, and list the kinds of "
        f"questions you can answer."
    ),
    datasource_references=datasource_references,
    glossary_terms=glossary_terms,
    example_queries=example_queries,
)


# Create the Data Agent
data_agent = geminidataanalytics.DataAgent(
    data_analytics_agent=geminidataanalytics.DataAnalyticsAgent(
        published_context=published_context
    ),
)

create_request = geminidataanalytics.CreateDataAgentRequest(
    parent=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}",
    data_agent_id=CA_AGENT_ID,
    data_agent=data_agent,
)

print(f"Deleting existing Data Agent '{CA_AGENT_ID}' if it exists...")
try:
    data_agent_client.delete_data_agent(name=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}/dataAgents/{CA_AGENT_ID}")
    print("Existing Data Agent deleted or deletion initiated.")
except Exception as e:
    print(f"Failed to delete existing Data Agent (might not exist): {e}")

print(f"Creating Data Agent '{CA_AGENT_ID}'...")
ca_agent = data_agent_client.create_data_agent_sync(request=create_request)

conv_request = geminidataanalytics.CreateConversationRequest(
    parent=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}",
    conversation=geminidataanalytics.Conversation(
        agents=[ca_agent.name]
    )
)


ca_conversation = data_chat_client.create_conversation(request=conv_request)
