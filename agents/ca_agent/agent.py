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
from google.adk.planners import BuiltInPlanner
from google.genai.types import ThinkingConfig
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryAgentAnalyticsPlugin
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.tool_context import ToolContext
from custom_tools import list_code_files, read_code_file, run_gemini_cli
from mcp_tools import search_developer_knowledge, get_developer_knowledge_document

# Two clients: one manages Data Agents, the other handles conversations
data_agent_client = geminidataanalytics.DataAgentServiceClient()
data_chat_client = geminidataanalytics.DataChatServiceClient()

import uuid as _uuid
_run_id = _uuid.uuid4().hex[:8]
CA_CONVERSATION_ID=f"agent_ops_conv_{_run_id}"
CA_AGENT_ID=f"ca_agent_ops_{_run_id}"
# --- Initialize the Plugin ---
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
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

from google.genai.types import HttpRetryOptions

# Define robust exponential backoff strategy for 429 RESOURCE_EXHAUSTED errors
api_retry_options = HttpRetryOptions(
    attempts=10,
    initial_delay=2.0,
    max_delay=60.0,
    exp_base=2.0,
    jitter=0.5,
    http_status_codes=[429, 500, 502, 503, 504]
)

llm = Gemini(
    model="gemini-2.5-flash",
    retry_options=api_retry_options
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
        f"Use CURRENT_TIMESTAMP() for current time comparisons in queries.\n\n"
        f"**CODE INSPECTION & FIXES:**\n"
        f"You have access to the local project codebase through `list_code_files` and `read_code_file`. "
        f"When you identify a failing tool or agent via BigQuery telemetry, use these tools to read the actual Python code responsible. "
        f"Analyze the code against the error and propose a concrete code fix.\n"
        f"You also have access to the `run_gemini_cli` tool to execute `gemini` CLI commands if needed.\n\n"
        f"**DEVELOPER DOCUMENTATION ACCESS:**\n"
        f"You have access to the Developer Knowledge MCP server to search and retrieve official Google developer documentation, including APIs, code snippets, release notes, best practices, guides, and debugging info. "
        f"Use the `search_developer_knowledge` tool to find document snippets and names mapping to your interest. "
        f"Use the `get_developer_knowledge_document` tool with a list of document names (parents) found in the search results to retrieve full document content. "
        f"Prefer this over external internet searches for official Google developer inquiries."
    ),
    tools=[bigquery_toolset, set_state, list_code_files, read_code_file, run_gemini_cli, search_developer_knowledge,
           get_developer_knowledge_document],
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(include_thoughts=True)
    ),
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

from example_queries import example_queries, glossary_terms

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
    if "404" in str(e) or "Not Found" in str(e) or "NotFound" in type(e).__name__:
        pass
    else:
        print(f"Failed to delete existing Data Agent: {e}")

print(f"Creating Data Agent '{CA_AGENT_ID}'...")
ca_agent = data_agent_client.create_data_agent_sync(request=create_request)

conv_request = geminidataanalytics.CreateConversationRequest(
    parent=f"projects/{PROJECT_ID}/locations/{CA_LOCATION}",
    conversation=geminidataanalytics.Conversation(
        agents=[ca_agent.name]
    )
)


ca_conversation = data_chat_client.create_conversation(request=conv_request)
