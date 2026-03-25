# Conversational Analytics Agent

The Conversational Analytics (CA) agent is designed to answer natural language questions about the telemetry data collected by the ADK BigQuery Analytics Plugin. It uses the `geminidataanalytics` (v1alpha) library to translate questions into SQL and execute them against BigQuery.

## Prerequisites

- [ ] Ensure the `.env` file in the project root is properly configured with your BigQuery project, dataset, and table details.
- [ ] The agent relies on a set of normalized views described below.

## Configuration

The agent is configured in `agents/ca_agent/agent.py`. It uses a set of predefined views to structure its responses and queries.

### Supported Views

The agent is aware of and can query the following views:

- `invocation_events_view`: End-to-end latency and status for root invocations.
- `agent_events_view`: Performance metrics for individual sub-agents.
- `llm_events_view`: Detailed telemetry for LLM inference (tokens, latency).
- `tool_events_view`: Performance metrics for external tool executions.

## Usage

### Testing the Agent

You can test the agent's ability to answer questions using the provided `test_ca_agent.py` script.

1.  **Activate Virtual Environment**:
    ```bash
    source .venv/bin/activate
    ```
2.  **Run Tests**:
    ```bash
    python3 test_ca_agent.py
    ```

### Example Queries and Expected SQL

The following are examples of questions you can ask the agent and the expected SQL it should generate.

#### 1. End-to-End Performance

**Question:** What is the P95 latency for the `knowledge_qa_supervisor` agent?
**Expected SQL:**
```sql
SELECT APPROX_QUANTILES(duration_ms, 1000)[OFFSET(950)] as p95_ms
FROM `agent-operations-ek-05.logging.invocation_events_view`
WHERE root_agent_name = 'knowledge_qa_supervisor'
```

#### 2. Agent Performance

**Question:** Show me the error rate for each agent.
**Expected SQL:**
```sql
SELECT agent_name, COUNTIF(status = 'ERROR') / COUNT(*) * 100 as error_rate_pct
FROM `agent-operations-ek-05.logging.agent_events_view`
GROUP BY agent_name
ORDER BY error_rate_pct DESC
```

#### 3. Tool Performance

**Question:** What are the most used tools?
**Expected SQL:**
```sql
SELECT tool_name, COUNT(*) as usage_count
FROM `agent-operations-ek-05.logging.tool_events_view`
GROUP BY tool_name
ORDER BY usage_count DESC
```

#### 4. LLM Performance

**Question:** What is the average token count for each model?
**Expected SQL:**
```sql
SELECT model_name, AVG(total_token_count) as avg_tokens
FROM `agent-operations-ek-05.logging.llm_events_view`
GROUP BY model_name
ORDER BY avg_tokens DESC
```

#### 5. Bottlenecks

**Question:** Show me the slowest tool executions.
**Expected SQL:**
```sql
SELECT tool_name, duration_ms, trace_id, span_id
FROM `agent-operations-ek-05.logging.tool_events_view`
ORDER BY duration_ms DESC
LIMIT 5
```

## Adding More Examples

To improve the agent's accuracy for specific query types, you can add more `ExampleQuery` instances to the `published_context` in `agents/ca_agent/agent.py`.

```python
published_context = PublishedContext(
    example_queries=[
        ExampleQuery(
            natural_language_query="Show me the average latency for each model.",
            sql_query="SELECT model_name, AVG(duration_ms) FROM `agent-operations-ek-05.logging.llm_events_view` GROUP BY model_name"
        ),
        # Add your new example here
    ]
)
```
