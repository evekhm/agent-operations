# Conversational Analytics Agent

The Conversational Analytics (CA) agent, also known as the **Agent Operations Observability Analyst**, is designed to answer natural language questions about the telemetry data collected by the ADK BigQuery Analytics Plugin. It uses the `geminidataanalytics` (v1alpha) library to translate questions into SQL and execute them against BigQuery.

## Prerequisites

- [ ] Ensure the `.env` file in the project root is properly configured with your BigQuery project, dataset, and table details.
- [ ] The agent relies on a set of normalized views described below.
- [ ] To connect with MCP server, you need to enable the Developer Knowledge API and Create and Secure an API Key
    - [ ] Enable Developer Knowledge API
    - [ ] Create and Secure an API Key by Navigate to Console → APIs & Services → Credentials → Create credentials → API key. 
    - [ ] Add to .env or load into the environment: 
    ```bash
        export DEVELOPER_KNOWLEDGE_API_KEY="<your-api-key>"
    ```
    
    

## Configuration

The agent is configured in `agents/ca_agent/agent.py`. It uses a set of predefined views to structure its responses and queries.

### Supported Views

The agent is aware of and can query the following views:

1. `agent_events_view`: Agent execution lifecycle (start, end, latency, errors per span).
2. `invocation_events_view`: End-to-end invocation (user turn) metrics including user message.
3. `llm_events_view`: Detailed telemetry for LLM inference (tokens, latency).
4. `tool_events_view`: Performance metrics for external tool executions.

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

The following are examples of questions you can ask the agent and the expected SQL it should generate. By using the `CURRENT_TIMESTAMP()` function and dynamic environment variables, the agent generates queries resilient to schema or project redeployments.

#### 1. End-to-End Performance
**Question:** What is the P95 latency for the `knowledge_qa_supervisor` agent?
**Expected SQL:**
```sql
SELECT
    APPROX_QUANTILES(duration_ms, 100)[OFFSET(95)] AS p95_latency,
    AVG(duration_ms) AS avg_latency
FROM `{PROJECT_ID}.{DATASET_ID}.{INVOCATION_EVENTS_VIEW}` AS T
WHERE root_agent_name = 'knowledge_qa_supervisor'
    AND T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
```

#### 2. Agent Performance
**Question:** Show me the error rate for each agent.
**Expected SQL:**
```sql
SELECT
    agent_name,
    COUNTIF(status = 'ERROR') / COUNT(*) * 100 AS error_rate_pct
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS T
WHERE T.timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) AND CURRENT_TIMESTAMP()
GROUP BY agent_name
ORDER BY error_rate_pct DESC
```

#### 3. Execution Bottlenecks
**Question:** Find the 5 slowest component executions in recent invocations.
**Expected SQL:**
```sql
SELECT
    span_id,
    agent_name,
    duration_ms,
    timestamp
FROM `{PROJECT_ID}.{DATASET_ID}.{AGENT_EVENTS_VIEW}` AS A
WHERE A.duration_ms > 0
    AND A.agent_name != A.root_agent_name
ORDER BY A.timestamp DESC, A.span_id ASC
LIMIT 5
```

## Adding More Examples

To improve the agent's accuracy for specific query types, you can add more `ExampleQuery` instances to the `published_context` inside `agents/ca_agent/agent.py`.

```python
import google.cloud.geminidataanalytics as geminidataanalytics

published_context = geminidataanalytics.Context(
    example_queries=[
        geminidataanalytics.ExampleQuery(
            natural_language_question="Show me the average latency for each model.",
            sql_query=f"""
SELECT model_name, AVG(duration_ms)
FROM `{PROJECT_ID}.{DATASET_ID}.{LLM_EVENTS_VIEW}`
GROUP BY model_name
"""
        ),
        # Add your new example here
    ]
)
```
