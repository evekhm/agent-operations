# BigQuery Observability Glossary & Schemas

This document provides a detailed explanation of the BigQuery tables and views used by the Conversational Analytics Agent, along with their schemas and semantic meanings.

## Terminology

*   **Session**: A single conversation thread between a user and the agent, identified by `session_id`.
*   **Invocation**: A single request-response cycle within a session (one turn), identified by `invocation_id`. Generally corresponds to a user clicking "send".
*   **Agent Execution**: A period where an agent (root or sub-agent) is running. Identified by a span. One invocation can trigger multiple agent executions in a hierarchy.
*   **Tool Execution**: The running of a specific capability (e.g., querying a database, searching the web).
*   **LLM Call**: A request sent to a Large Language Model and the corresponding response.
*   **Status PENDING**: Indicates that an operation (invocation, agent, or tool) has started but has not yet completed. If an operation remains PENDING for longer than a configured timeout (e.g., 5 minutes), it may be interpreted as an error or crash.
*   **Status OK**: The operation completed successfully.
*   **Status ERROR**: The operation failed.

## Base Table: `agent_events_demo_v3`

The raw event stream captured by the BigQuery Agent Analytics Plugin.

### Schema

*   **timestamp**: TIMESTAMP (REQUIRED) - The UTC timestamp when the event occurred.
*   **event_type**: STRING (NULLABLE) - The category of the event (e.g., 'LLM_REQUEST', 'TOOL_STARTING', 'AGENT_COMPLETED').
*   **agent**: STRING (NULLABLE) - The name of the agent that generated this event.
*   **session_id**: STRING (NULLABLE) - A unique identifier for the entire conversation session.
*   **invocation_id**: STRING (NULLABLE) - A unique identifier for a single turn or execution within a session.
*   **user_id**: STRING (NULLABLE) - The identifier of the end-user.
*   **trace_id**: STRING (NULLABLE) - OpenTelemetry trace ID for distributed tracing.
*   **span_id**: STRING (NULLABLE) - OpenTelemetry span ID for this specific operation.
*   **parent_span_id**: STRING (NULLABLE) - OpenTelemetry parent span ID.
*   **content**: JSON (NULLABLE) - The primary payload of the event. Structure depends on `event_type`.
*   **content_parts**: RECORD (REPEATED) - For multi-modal events, contains a list of content parts.
*   **attributes**: JSON (NULLABLE) - A JSON object containing arbitrary key-value pairs for additional event metadata (e.g., model, usage).
*   **latency_ms**: JSON (NULLABLE) - A JSON object containing latency measurements ('total_ms', 'time_to_first_token_ms').
*   **status**: STRING (NULLABLE) - The outcome of the event ('OK' or 'ERROR').
*   **error_message**: STRING (NULLABLE) - Detailed error message if status is 'ERROR'.
*   **is_truncated**: BOOLEAN (NULLABLE) - Indicates if the 'content' field was truncated.

## Views

Semantic layer on top of `agent_events_demo_v3`.

### 1. `invocation_events_view`

Aggregates information about Agent Invocations. Combines lifecycle events (STARTING, COMPLETED) with the User Message.

#### Schema

*   **timestamp**: TIMESTAMP - The start timestamp of the invocation.
*   **root_agent_name**: STRING - The designated root agent for this invocation.
*   **agent_name**: STRING - The name of the agent that started the invocation.
*   **content_text_summary**: STRING - A summary of the user's input message.
*   **content_text**: STRING - The primary text of the user's input.
*   **duration_ms**: INTEGER - Total time in milliseconds from starting to completion.
*   **status**: STRING - execution status ('OK', 'ERROR', or 'PENDING').
*   **error_message**: STRING - Exception message if error.
*   **message_timestamp**: TIMESTAMP - When the user message was received.
*   **start_timestamp**: TIMESTAMP - Exact start timestamp.
*   **end_timestamp**: TIMESTAMP - Exact end timestamp.
*   **invocation_id**: STRING - Unique ID for this specific run.
*   **session_id**: STRING - ID of the multi-turn session.
*   **trace_id**: STRING - OpenTelemetry trace ID.
*   **span_id**: STRING - OpenTelemetry span ID.
*   **user_id**: STRING - ID of the user.

### 2. `agent_events_view`

Tracks the execution lifecycle of agents. Insighted into latency, instructions, and flow.

#### Schema

*   **timestamp**: TIMESTAMP - Timestamp of AGENT_STARTING.
*   **root_agent_name**: STRING - Name of the root agent.
*   **agent_name**: STRING - Name of the agent executing this span.
*   **instruction**: JSON - Instruction or input provided to the agent.
*   **duration_ms**: INTEGER - Total time in milliseconds.
*   **status**: STRING - Execution status ('OK', 'ERROR', or 'PENDING').
*   **error_message**: STRING - Exception message if error.
*   **span_id**: STRING - OpenTelemetry span_id.
*   **trace_id**: STRING - OpenTelemetry trace_id.
*   **parent_span_id**: STRING - OpenTelemetry parent_span_id.
*   **user_id**: STRING - ID of the user.
*   **session_id**: STRING - ID of multi-turn session.
*   **start_timestamp**: TIMESTAMP - Exact start timestamp.
*   **end_timestamp**: TIMESTAMP - Exact end timestamp.

### 3. `llm_events_view`

Isolates LLM interactions (requests and responses).

#### Schema

*   **timestamp**: TIMESTAMP - Timestamp of LLM_REQUEST.
*   **root_agent_name**: STRING - Name of root agent.
*   **agent_name**: STRING - Name of agent making the call.
*   **llm_config**: JSON - LLM configuration.
*   **usage_metadata**: JSON - Token usage metrics.
*   **model_name**: STRING - Model name (specific version if available).
*   **requested_model**: STRING - Model name requested.
*   **response_model**: STRING - Model version returned.
*   **duration_ms**: FLOAT - Total time in milliseconds.
*   **time_to_first_token_ms**: FLOAT - Time to first token.
*   **status**: STRING - Outcome ('OK' or 'ERROR').
*   **error_message**: STRING - Exception message if failed.
*   **prompt_token_count**: INTEGER - Input prompt tokens.
*   **candidates_token_count**: INTEGER - Generated response tokens.
*   **total_token_count**: INTEGER - Total tokens.
*   **thoughts_token_count**: INTEGER - Thinking/reasoning tokens.
*   **full_request**: JSON - Raw JSON content of request.
*   **full_response**: JSON - Raw JSON content of response.
*   **request_text**: STRING - Extracted text portion of prompt.
*   **response_text**: STRING - Extracted text portion of model's response.
*   **span_id**: STRING - OpenTelemetry span_id.
*   **trace_id**: STRING - OpenTelemetry trace_id.
*   **parent_span_id**: STRING - OpenTelemetry parent span_id.
*   **user_id**: STRING - ID of the user.
*   **session_id**: STRING - ID of multi-turn session.
*   **start_timestamp**: TIMESTAMP - Exact start timestamp.
*   **end_timestamp**: TIMESTAMP - Exact end timestamp.

### 4. `tool_events_view`

Specialized view for tool execution events.

#### Schema

*   **timestamp**: TIMESTAMP - Timestamp of TOOL_STARTING.
*   **root_agent_name**: STRING - Name of root agent.
*   **agent_name**: STRING - Name of agent executing tool.
*   **tool_name**: STRING - Name of executed tool.
*   **tool_args**: JSON - Arguments passed to tool.
*   **tool_result**: JSON - Tool result on success.
*   **duration_ms**: INTEGER - Total time in milliseconds.
*   **error_message**: STRING - Exception message if failed.
*   **status**: STRING - Execution status ('OK', 'ERROR', or 'PENDING').
*   **span_id**: STRING - OpenTelemetry span_id.
*   **trace_id**: STRING - OpenTelemetry trace_id.
*   **parent_span_id**: STRING - OpenTelemetry parent span_id.
*   **user_id**: STRING - ID of user.
*   **session_id**: STRING - ID of multi-turn session.
*   **start_timestamp**: TIMESTAMP - Exact start timestamp.
*   **end_timestamp**: TIMESTAMP - Exact end timestamp.
