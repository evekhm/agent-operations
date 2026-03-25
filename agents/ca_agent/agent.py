from google.cloud import geminidataanalytics
from config import PROJECT_ID, CA_CONVERSATION_ID, CA_AGENT_ID, DATASET_ID, TABLE_ID
import pandas as pd
from google.cloud import geminidataanalytics
# Import Libraries & Initialize Plugin, Tools, Models and Agent
import google.auth
import os
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.google_llm import Gemini
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryAgentAnalyticsPlugin
from google.adk.tools.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.tools.tool_context import ToolContext

# Two clients: one manages Data Agents, the other handles conversations
data_agent_client = geminidataanalytics.DataAgentServiceClient()
data_chat_client = geminidataanalytics.DataChatServiceClient()
CA_LOCATION = "global"  # CA API always uses global

# --- Initialize the Plugin ---
bq_logging_plugin = BigQueryAgentAnalyticsPlugin(
    project_id=PROJECT_ID,  # project_id is required input from user
    dataset_id=DATASET_ID,  # dataset_id is required input from user
    table_id=TABLE_ID,
    # Optional: defaults to "agent_events". The plugin automatically creates
    # this table if it doesn't exist.
)
print(f"BigQueryAgentAnalyticsPlugin initialized, streaming data to {PROJECT_ID}:{DATASET_ID}.{TABLE_ID}")

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
    name="my_bq_agent",
    instruction=(
            "You are a helpful assistant with access to BigQuery tools. "
            "When users ask about NYC Citi Bike data, query the public dataset "
            "`bigquery-public-data.new_york_citibike.citibike_trips` and "
            "`bigquery-public-data.new_york_citibike.citibike_stations`. "
            "Always use the user's project for billing: " + PROJECT_ID + ". "
                                                                         "You can also set session state using the `set_state` tool."
    ),
    tools=[bigquery_toolset, set_state],
    generate_content_config={
        "temperature": 0.5,
        "top_p": 0.9,
    },
)

# --- Create the App ---
app = App(
    name="my_bq_agent",
    root_agent=root_agent,
    plugins=[bq_logging_plugin], # Register the plugin here
)
print(f"my_bq_agent initialized for project {PROJECT_ID}, dataset {DATASET_ID}")

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
bq_table_ref = geminidataanalytics.BigQueryTableReference(
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    table_id=TABLE_ID,
    schema=geminidataanalytics.Schema(
        description="Agent event logs auto-captured by the BigQuery Agent Analytics Plugin. Each row is one event in an agent's lifecycle.",
        fields=[
            geminidataanalytics.Field(name="timestamp", description="When the event occurred (UTC)"),
            geminidataanalytics.Field(name="event_type",
                                      description="Type of agent event: USER_MESSAGE_RECEIVED, LLM_REQUEST, LLM_RESPONSE, TOOL_STARTING, TOOL_COMPLETED, TOOL_ERROR, INVOCATION_STARTING, AGENT_COMPLETED"),
            geminidataanalytics.Field(name="agent", description="Name of the agent that produced this event"),
            geminidataanalytics.Field(name="session_id", description="Unique identifier for the user session"),
            geminidataanalytics.Field(name="invocation_id",
                                      description="Unique identifier for one user-to-agent invocation within a session"),
            geminidataanalytics.Field(name="user_id", description="Identifier for the user who triggered the event"),
            geminidataanalytics.Field(name="content",
                                      description="JSON payload whose structure varies by event_type (e.g., text_summary for user messages, tool name for tool events, response for LLM responses)"),
            geminidataanalytics.Field(name="latency_ms",
                                      description="JSON field containing total_ms (total latency in milliseconds) and time_to_first_token_ms"),
            geminidataanalytics.Field(name="status", description="Outcome status of the event (e.g., success, error)"),
            geminidataanalytics.Field(name="error_message",
                                      description="Error details if the event failed, NULL otherwise"),
            geminidataanalytics.Field(name="attributes",
                                      description="JSON field with additional metadata and attributes"),
            geminidataanalytics.Field(name="trace_id", description="Distributed tracing trace ID"),
            geminidataanalytics.Field(name="span_id", description="Distributed tracing span ID"),
            geminidataanalytics.Field(name="content_parts",
                                      description="Structured content parts with text, function calls, and function responses"),
            geminidataanalytics.Field(name="messages", description="Message-level content with role and parts"),
        ],
    ),
)

datasource_references = geminidataanalytics.DatasourceReferences(
    bq=geminidataanalytics.BigQueryTableReferences(table_references=[bq_table_ref])
)

# Define glossary terms for domain-specific vocabulary
glossary_terms = [
    geminidataanalytics.GlossaryTerm(
        display_name="event_type",
        description="The type of agent event. Values include: USER_MESSAGE_RECEIVED (user sent a message), LLM_REQUEST (request sent to the LLM), LLM_RESPONSE (response received from LLM), TOOL_STARTING (tool execution began), TOOL_COMPLETED (tool execution finished), TOOL_ERROR (tool execution failed), INVOCATION_STARTING (new invocation began), AGENT_COMPLETED (agent finished processing)",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="latency_ms",
        description="JSON field containing total_ms (total latency from start to finish in milliseconds) and time_to_first_token_ms (time until the first token was generated)",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="content",
        description="JSON payload that varies by event_type. For USER_MESSAGE_RECEIVED: contains text_summary. For TOOL_COMPLETED: contains tool name. For LLM_RESPONSE: contains response text.",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="session",
        description="A single conversation between a user and the agent, identified by session_id",
    ),
    geminidataanalytics.GlossaryTerm(
        display_name="invocation",
        description="One user-to-agent request-response cycle within a session, identified by invocation_id",
    ),
]

example_queries = [
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show usage monitoring — daily active users, sessions, invocations, and average latency",
        sql_query=f"""SELECT DATE(timestamp) AS usage_date, COUNT(DISTINCT user_id) AS unique_active_users, COUNT(DISTINCT session_id) AS total_sessions, COUNTIF(event_type = 'INVOCATION_STARTING') AS total_invocations, ROUND(AVG(SAFE_CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64)), 2) AS avg_completion_latency_ms FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` GROUP BY usage_date ORDER BY usage_date DESC""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Show all errors with timestamps and error messages",
        sql_query=f"""SELECT timestamp, session_id, event_type, error_message FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE error_message IS NOT NULL ORDER BY timestamp DESC LIMIT 10""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Analyze performance by event type — show average, max, and p99 latency",
        sql_query=f"""
        SELECT event_type, ROUND(AVG(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS FLOAT64)) / 1000, 2) AS avg_latency_sec,
         ROUND(MAX(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS FLOAT64)) / 1000, 2) AS max_latency_sec, 
         COUNT(*) AS event_count 
         FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` 
         WHERE agent = 'my_bq_agent' AND latency_ms IS NOT NULL 
         GROUP BY event_type ORDER BY avg_latency_sec DESC""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Which tool calls have the highest latency?",
        sql_query=f"""SELECT JSON_VALUE(content, '$.tool') AS tool_name, 
        ROUND(SAFE_CAST(JSON_VALUE(latency_ms, '$.total_ms') AS FLOAT64) / 1000, 2) AS latency_sec, 
        timestamp, session_id, user_id FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` 
        WHERE event_type = 'TOOL_COMPLETED' AND agent = 'my_bq_agent' AND 
        latency_ms IS NOT NULL ORDER BY latency_sec DESC LIMIT 10""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Detect latency anomalies in agent completion events",
        sql_query=f"""WITH base_data AS (SELECT DATE_TRUNC(timestamp, MINUTE) AS event_minute, AVG(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS FLOAT64)) AS avg_latency_ms FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE agent = 'my_bq_agent' AND event_type = 'AGENT_COMPLETED' AND latency_ms IS NOT NULL GROUP BY 1), historical_data AS (SELECT event_minute, avg_latency_ms FROM base_data ORDER BY event_minute LIMIT 50), target_data AS (SELECT event_minute, avg_latency_ms FROM base_data ORDER BY event_minute DESC LIMIT 10) SELECT time_series_timestamp, time_series_data, is_anomaly, lower_bound, upper_bound, anomaly_probability FROM AI.DETECT_ANOMALIES((SELECT * FROM historical_data), (SELECT * FROM target_data), data_col => 'avg_latency_ms', timestamp_col => 'event_minute') ORDER BY time_series_timestamp DESC""",
    ),
    geminidataanalytics.ExampleQuery(
        natural_language_question="Classify user messages by intent and show the distribution",
        sql_query=f"""WITH user_messages AS (SELECT timestamp, user_id, JSON_VALUE(content, '$.text_summary') AS raw_message FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` WHERE agent = 'my_bq_agent' AND event_type = 'USER_MESSAGE_RECEIVED' AND JSON_VALUE(content, '$.text_summary') IS NOT NULL LIMIT 50) SELECT user_id, raw_message, AI.CLASSIFY(raw_message, categories => ['Trend Analysis', 'Data Exploration', 'Location Service', 'Security', 'Other'], connection_id => '{PROJECT_ID}.{CONNECTION_ID}', endpoint => 'gemini-2.5-flash') AS ai_intent FROM user_messages""",
    ),
]

published_context = geminidataanalytics.Context(
    system_instruction=(
        "You are an agent operations analyst. This table contains event logs "
        "from an AI agent (my_bq_agent) that helps users query NYC Citi Bike data. "
        "The logs are auto-captured by the BigQuery Agent Analytics Plugin. "
        "Help the user understand agent behavior, performance, errors, and usage patterns."
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

ca_agent = data_agent_client.create_data_agent_sync(request=create_request)
ca_conversation = data_chat_client.create_conversation(request=conv_request)
