"""Shared quality evaluation logic used by both the standalone SDK script
(query_responses.py) and the report generation pipeline (quality_evaluation.py).

Contains:
- Metric definitions (response_usefulness, task_grounding)
- SDK client + config setup
- Trace-based response resolution (A2A, time-window fallback)
- Evaluation runner
"""
import json
import logging
import os

from agents.observability_agent.config import (
    PROJECT_ID,
    DATASET_ID,
    TABLE_ID,
    DATASET_LOCATION,
)

logger = logging.getLogger(__name__)

EVAL_MODEL_ID = os.getenv("EVAL_MODEL_ID", "gemini-2.5-flash")


# ---------------------------------------------------------------------------
# SDK client
# ---------------------------------------------------------------------------

def get_client():
    from bigquery_agent_analytics import Client
    return Client(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        table_id=TABLE_ID,
        location=DATASET_LOCATION,
    )


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

def get_eval_metrics():
    from bigquery_agent_analytics import (
        CategoricalMetricCategory,
        CategoricalMetricDefinition,
    )

    response_usefulness = CategoricalMetricDefinition(
        name="response_usefulness",
        definition=(
            "Whether the agent's final response provides a genuinely useful, "
            "substantive answer to the user's question. A response that apologizes, "
            "says it cannot help, returns no data, provides only generic filler, "
            "or loops without resolving the question is NOT useful."
        ),
        categories=[
            CategoricalMetricCategory(
                name="meaningful",
                definition=(
                    "The response directly and substantively addresses the user's "
                    "question with specific, actionable information."
                ),
            ),
            CategoricalMetricCategory(
                name="false_positive",
                definition=(
                    "The response technically succeeded (no error) but does NOT "
                    "meaningfully answer the user's question. Examples: apologies, "
                    "'I don't have that information', empty data results, generic "
                    "filler text, or the agent looping without a resolution."
                ),
            ),
            CategoricalMetricCategory(
                name="partial",
                definition=(
                    "The response partially addresses the question but is "
                    "incomplete, missing key details, or only tangentially relevant."
                ),
            ),
        ],
    )

    task_grounding = CategoricalMetricDefinition(
        name="task_grounding",
        definition=(
            "Whether the agent's response is grounded in actual data retrieved "
            "from its tools, or is fabricated / hallucinated general knowledge."
        ),
        categories=[
            CategoricalMetricCategory(
                name="grounded",
                definition=(
                    "The response is clearly based on data retrieved from the "
                    "agent's tools (search results, database lookups, API calls)."
                ),
            ),
            CategoricalMetricCategory(
                name="ungrounded",
                definition=(
                    "The response appears to be fabricated or based on the LLM's "
                    "general knowledge rather than actual tool results. The tool "
                    "may have returned empty data and the agent filled in anyway."
                ),
            ),
            CategoricalMetricCategory(
                name="no_tool_needed",
                definition=(
                    "The question did not require tool usage and a direct LLM "
                    "response was appropriate."
                ),
            ),
        ],
    )

    return [response_usefulness, task_grounding]


# ---------------------------------------------------------------------------
# Trace helpers — extract Q&A and resolve A2A responses
# ---------------------------------------------------------------------------

def get_user_input(trace) -> str:
    """Extract the user's question from a trace."""
    for span in trace.spans:
        if span.event_type == "USER_MESSAGE_RECEIVED":
            c = span.content
            if isinstance(c, dict):
                return c.get("text_summary") or c.get("text") or ""
            elif c:
                return str(c)
    return ""


def get_responding_agent(trace) -> str:
    """Determine which agent produced the final response."""
    for span in reversed(trace.spans):
        if span.event_type == "LLM_RESPONSE":
            c = span.content
            if isinstance(c, dict):
                resp = c.get("response", "")
                if resp and not resp.startswith("call:"):
                    return span.agent or "unknown"
    return "no_response"


def _is_single_word_routing(response: str) -> bool:
    """Check if a response is a single-word routing/classification output."""
    if not response:
        return True
    stripped = response.strip()
    return len(stripped.split()) <= 1 and len(stripped) < 20


def _extract_a2a_text(payload) -> tuple:
    """Extract response text and agent name from an A2A_INTERACTION payload.

    Returns:
        (response_text, agent_name)
    """
    if not isinstance(payload, dict):
        return (str(payload) if payload else None), None

    text_parts = []
    for artifact in payload.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("kind") == "text" and part.get("text"):
                text_parts.append(part["text"])

    if not text_parts:
        for msg in payload.get("history", []):
            if msg.get("role") == "agent":
                for part in msg.get("parts", []):
                    if part.get("kind") == "text" and part.get("text"):
                        text_parts.append(part["text"])

    meta = payload.get("metadata", {})
    agent_name = meta.get("adk_app_name") or meta.get("adk_author")
    text = " ".join(text_parts) if text_parts else None
    return text, agent_name


def get_a2a_response(trace) -> tuple:
    """Extract response from A2A_INTERACTION events.

    Returns:
        (response_text, agent_name) or (None, None) if no A2A_INTERACTION found.
    """
    for span in reversed(trace.spans):
        if span.event_type == "A2A_INTERACTION":
            c = span.content
            if isinstance(c, dict):
                text, agent = _extract_a2a_text(c)
                if text:
                    return text, agent or span.agent or "remote_agent"
            elif isinstance(c, str):
                try:
                    parsed = json.loads(c)
                    text, agent = _extract_a2a_text(parsed)
                    if text:
                        return text, agent or span.agent or "remote_agent"
                except (json.JSONDecodeError, TypeError):
                    return c, span.agent or "remote_agent"
    return None, None


def get_transfer_info(trace) -> dict:
    """Detect if the trace transferred to a remote A2A agent.

    Returns dict with remote_agent, agent_start, agent_end times,
    or empty dict if no transfer.
    """
    for span in trace.spans:
        if span.event_type == "TOOL_STARTING":
            c = span.content
            if isinstance(c, dict) and c.get("tool") == "transfer_to_agent":
                tool_origin = c.get("tool_origin", "")
                remote_agent = c.get("args", {}).get("agent_name")
                if not remote_agent:
                    continue
                if tool_origin == "TRANSFER_AGENT":
                    continue
                agent_start, agent_end = _find_agent_window(trace, remote_agent)
                if agent_start and agent_end:
                    return {
                        "remote_agent": remote_agent,
                        "agent_start": agent_start,
                        "agent_end": agent_end,
                    }

    # Fallback: detect remote agents with no LLM_RESPONSE
    agents_with_response = set()
    for span in trace.spans:
        if span.event_type == "LLM_RESPONSE" and span.agent:
            agents_with_response.add(span.agent)

    seen_agents = {}
    for span in trace.spans:
        if span.event_type in ("AGENT_STARTING", "AGENT_COMPLETED") and span.agent:
            seen_agents.setdefault(span.agent, {})[span.event_type] = span.timestamp

    for agent_name, events in seen_agents.items():
        if agent_name in agents_with_response:
            continue
        agent_start = events.get("AGENT_STARTING")
        agent_end = events.get("AGENT_COMPLETED")
        if agent_start and agent_end:
            return {
                "remote_agent": agent_name,
                "agent_start": agent_start,
                "agent_end": agent_end,
            }

    return {}


def _find_agent_window(trace, agent_name):
    """Find AGENT_STARTING/COMPLETED timestamps for a given agent."""
    agent_start = None
    agent_end = None
    for s in trace.spans:
        if s.agent == agent_name:
            if s.event_type == "AGENT_STARTING":
                agent_start = s.timestamp
            elif s.event_type == "AGENT_COMPLETED":
                agent_end = s.timestamp
    return agent_start, agent_end


def resolve_remote_response(client, transfer_info) -> str:
    """Find the remote A2A agent's response using a time-window query."""
    from google.cloud import bigquery as bq

    query = f"""
        SELECT JSON_VALUE(content, '$.response') AS response
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE agent = @remote_agent
          AND event_type = 'LLM_RESPONSE'
          AND JSON_VALUE(content, '$.response') IS NOT NULL
          AND JSON_VALUE(content, '$.response') NOT LIKE 'call:%'
          AND timestamp BETWEEN @start_time AND @end_time
        ORDER BY timestamp DESC
        LIMIT 1
    """
    params = [
        bq.ScalarQueryParameter("remote_agent", "STRING", transfer_info["remote_agent"]),
        bq.ScalarQueryParameter("start_time", "TIMESTAMP", transfer_info["agent_start"]),
        bq.ScalarQueryParameter("end_time", "TIMESTAMP", transfer_info["agent_end"]),
    ]
    job_config = bq.QueryJobConfig(query_parameters=params)
    rows = list(client.bq_client.query(query, job_config=job_config).result())
    if rows:
        return rows[0].get("response", "")
    return ""


# ---------------------------------------------------------------------------
# Resolve responses for a batch of traces
# ---------------------------------------------------------------------------

def resolve_trace_responses(client, traces):
    """Process traces: extract Q&A, resolve A2A, track agent. Returns list of dicts."""
    results = []
    remote_lookups = 0

    for trace in traces:
        question = get_user_input(trace)
        if not question:
            continue

        response = trace.final_response
        if response:
            stripped = response.strip()
            if stripped.startswith("call:") or _is_single_word_routing(stripped):
                response = None
        answered_by = get_responding_agent(trace)
        is_a2a = False

        if not response:
            a2a_resp, a2a_agent = get_a2a_response(trace)
            if a2a_resp:
                response = a2a_resp
                answered_by = a2a_agent
                is_a2a = True
                remote_lookups += 1

        if not response:
            transfer = get_transfer_info(trace)
            if transfer:
                response = resolve_remote_response(client, transfer)
                if response:
                    answered_by = transfer["remote_agent"]
                    is_a2a = True
                    remote_lookups += 1

        latency_s = None
        if trace.total_latency_ms is not None:
            latency_s = round(trace.total_latency_ms / 1000, 1)

        results.append({
            "session_id": trace.session_id,
            "time": trace.start_time.strftime("%Y-%m-%d %H:%M:%S") if trace.start_time else "?",
            "question": question,
            "answered_by": answered_by,
            "response": (response or ""),
            "latency_s": latency_s,
            "is_a2a": is_a2a,
        })

    if remote_lookups:
        logger.info(f"Resolved {remote_lookups} A2A responses")

    return results


# ---------------------------------------------------------------------------
# Run evaluation (shared by standalone script and report generation)
# ---------------------------------------------------------------------------

def run_evaluation(time_range: str = None, limit: int = 100, model: str = None,
                   persist: bool = False) -> dict:
    """Runs categorical quality evaluation and returns a result dict.

    This is the core evaluation logic shared between:
    - query_responses.py (standalone CLI)
    - quality_evaluation.py (report generation pipeline)

    Args:
        time_range: Time window (e.g. "24h", "7d", "all", or None for all).
        limit: Maximum number of sessions to evaluate.
        model: Model endpoint for evaluation.
        persist: Whether to persist results to BigQuery.

    Returns:
        Dict with total_sessions, category_distributions, session_results
        (enriched with user_message/agent_response/is_a2a/answered_by),
        details, and created_at.
    """
    from bigquery_agent_analytics import (
        CategoricalEvaluationConfig,
        TraceFilter,
    )

    model = model or EVAL_MODEL_ID
    client = get_client()

    metrics = get_eval_metrics()
    cat_config = CategoricalEvaluationConfig(
        metrics=metrics,
        endpoint=model,
        temperature=0.0,
        include_justification=True,
        persist_results=persist,
        results_table="quality_eval_results" if persist else None,
    )

    # Build trace filter
    effective_time_range = time_range
    if effective_time_range and effective_time_range.lower() == "all":
        effective_time_range = None

    if effective_time_range:
        trace_filter = TraceFilter.from_cli_args(last=effective_time_range)
    else:
        trace_filter = TraceFilter()
    trace_filter.limit = limit

    # Run evaluation
    report = client.evaluate_categorical(
        config=cat_config,
        filters=trace_filter,
    )

    # Resolve responses for all evaluated sessions (for display context)
    all_session_ids = [sr.session_id for sr in report.session_results]
    logger.info(f"Resolving responses for {len(all_session_ids)} sessions...")

    traces = client.list_traces(
        filter_criteria=TraceFilter(session_ids=all_session_ids, limit=len(all_session_ids))
    )
    resolved = resolve_trace_responses(client, traces)
    resolved_map = {r["session_id"]: r for r in resolved}

    a2a_count = sum(1 for r in resolved if r.get("is_a2a"))

    # Build result dict
    result = {
        "total_sessions": report.total_sessions,
        "category_distributions": report.category_distributions,
        "details": report.details,
        "created_at": report.created_at.isoformat(),
        "a2a_sessions": a2a_count,
        "report": report,  # raw report for CLI display
        "resolved_map": resolved_map,  # raw resolved map for CLI display
        "session_results": [],
    }
    for sr in report.session_results:
        ctx = resolved_map.get(sr.session_id, {})
        sr_dict = {
            "session_id": sr.session_id,
            "user_message": ctx.get("question", ""),
            "agent_response": (ctx.get("response", ""))[:2000],
            "is_a2a": ctx.get("is_a2a", False),
            "answered_by": ctx.get("answered_by", ""),
            "metrics": [],
        }
        for mr in sr.metrics:
            sr_dict["metrics"].append({
                "metric_name": mr.metric_name,
                "category": mr.category,
                "justification": mr.justification,
                "parse_error": mr.parse_error,
                "raw_response": mr.raw_response,
            })
        result["session_results"].append(sr_dict)

    return result
