#!/usr/bin/env python3
"""Query user questions and agent responses using the BigQuery Agent Analytics SDK.

Handles both local sub-agents and remote A2A agents by detecting
transfer_to_agent tool calls and resolving the remote agent's response
via time-window matching.

Usage:
    python query_responses.py                # last 100 sessions
    python query_responses.py --limit 50
    python query_responses.py --eval         # include per-session quality evaluation
"""
import argparse
import logging
import os
import sys

dir_path = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(dir_path, "../.."))

from dotenv import load_dotenv
load_dotenv(os.path.join(dir_path, "../../.env"), override=True)

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("query_responses")

from agents.observability_agent.config import PROJECT_ID, DATASET_ID, TABLE_ID, DATASET_LOCATION


def get_client():
    from bigquery_agent_analytics import Client
    return Client(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        table_id=TABLE_ID,
        location=DATASET_LOCATION,
    )


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


def get_transfer_info(trace) -> dict:
    """Detect if the trace transferred to a remote A2A agent.

    Returns dict with remote_agent, agent_start, agent_end times,
    or empty dict if no transfer.

    Uses two strategies:
    1. Explicit: look for a transfer_to_agent tool call.
    2. Fallback: find AGENT_STARTING/COMPLETED pairs for non-supervisor
       agents that have no LLM_RESPONSE in this trace (i.e. the response
       lives in a separate session — the A2A trace gap).
    """
    # --- Strategy 1: explicit transfer_to_agent tool call ---
    for span in trace.spans:
        if span.event_type == "TOOL_STARTING":
            c = span.content
            if isinstance(c, dict) and c.get("tool") == "transfer_to_agent":
                remote_agent = c.get("args", {}).get("agent_name")
                if remote_agent:
                    agent_start, agent_end = _find_agent_window(trace, remote_agent)
                    if agent_start and agent_end:
                        return {
                            "remote_agent": remote_agent,
                            "agent_start": agent_start,
                            "agent_end": agent_end,
                        }

    # --- Strategy 2: fallback — detect remote agents with no LLM_RESPONSE ---
    # Collect agents that have LLM_RESPONSE spans in this trace
    agents_with_response = set()
    for span in trace.spans:
        if span.event_type == "LLM_RESPONSE" and span.agent:
            c = span.content
            if isinstance(c, dict):
                resp = c.get("response", "")
                if resp and not resp.startswith("call:"):
                    agents_with_response.add(span.agent)

    # Find AGENT_STARTING/COMPLETED pairs for agents without a response
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
            logger.debug(f"Fallback A2A detection: {agent_name} "
                         f"({agent_start} - {agent_end})")
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
    """Find the remote A2A agent's response using a time-window query.

    The remote agent logs its LLM events under a different session_id.
    We find them by matching agent name + timestamp within the supervisor's
    AGENT_STARTING/COMPLETED window.
    """
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


def main():
    parser = argparse.ArgumentParser(description="Query agent responses")
    parser.add_argument("--limit", type=int, default=100, help="Number of sessions (default: 100)")
    parser.add_argument("--eval", action="store_true", help="Run per-session quality evaluation")
    args = parser.parse_args()

    client = get_client()
    logger.info(f"Project: {PROJECT_ID}, Dataset: {DATASET_ID}, Table: {TABLE_ID}")

    # Fetch recent traces using the SDK
    from bigquery_agent_analytics import TraceFilter
    traces = client.list_traces(
        filter_criteria=TraceFilter(limit=args.limit)
    )
    logger.info(f"Fetched {len(traces)} sessions")

    # Process each trace
    results = []
    remote_lookups = 0
    for trace in traces:
        question = get_user_input(trace)
        if not question:
            continue

        response = trace.final_response
        answered_by = get_responding_agent(trace)

        # If no response found, check for A2A transfer and resolve
        if not response:
            transfer = get_transfer_info(trace)
            if transfer:
                response = resolve_remote_response(client, transfer)
                if response:
                    answered_by = transfer["remote_agent"]
                    remote_lookups += 1

        latency_s = None
        if trace.total_latency_ms is not None:
            latency_s = round(trace.total_latency_ms / 1000, 1)

        results.append({
            "session_id": trace.session_id,
            "time": trace.start_time.strftime("%Y-%m-%d %H:%M:%S") if trace.start_time else "?",
            "question": question[:120],
            "answered_by": answered_by,
            "response": (response or "")[:300],
            "latency_s": latency_s,
        })

    if remote_lookups:
        logger.info(f"Resolved {remote_lookups} remote A2A responses via time-window lookup")

    # Optional: run per-session evaluation
    if args.eval and results:
        logger.info("Running per-session quality evaluation...")
        _evaluate_results(client, results)

    # Print results
    _print_results(results)


def _evaluate_results(client, results):
    """Add per-session quality evaluation using the SDK's evaluate_categorical."""
    try:
        from bigquery_agent_analytics import (
            CategoricalEvaluationConfig,
            CategoricalMetricCategory,
            CategoricalMetricDefinition,
            TraceFilter,
        )

        session_ids = [r["session_id"] for r in results if r["response"]]
        if not session_ids:
            return

        metric = CategoricalMetricDefinition(
            name="quality",
            definition="Whether the agent's response is useful and answers the question.",
            categories=[
                CategoricalMetricCategory(name="good", definition="Directly answers with specific, actionable information."),
                CategoricalMetricCategory(name="partial", definition="Related but incomplete or not exactly what was asked."),
                CategoricalMetricCategory(name="bad", definition="Cannot help, no data, generic filler, or wrong topic."),
            ],
        )
        config = CategoricalEvaluationConfig(
            metrics=[metric],
            endpoint=os.getenv("EVAL_MODEL_ID", "gemini-2.5-flash"),
            temperature=0.0,
            include_justification=True,
        )
        report = client.evaluate_categorical(
            config=config,
            filters=TraceFilter(session_ids=session_ids),
        )

        # Map results back
        eval_map = {}
        for sr in report.session_results:
            for mr in sr.metrics:
                if mr.metric_name == "quality":
                    eval_map[sr.session_id] = f"{mr.category.upper()}: {mr.justification or ''}"[:200]

        for r in results:
            r["evaluation"] = eval_map.get(r["session_id"], "")

    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")


def _print_results(results):
    """Print results in a readable format."""
    if not results:
        print("\n  No sessions found.")
        return

    total = len(results)
    with_response = sum(1 for r in results if r["response"])
    no_response = total - with_response

    print(f"\n{'=' * 90}")
    print(f"  {total} sessions  |  {with_response} with response  |  {no_response} no response")
    print(f"{'=' * 90}")

    for r in results:
        print(f"\n  [{r['time']}] {r['session_id'][:16]}...")
        print(f"    Question:  {r['question']}")
        print(f"    Agent:     {r['answered_by']}")
        if r["response"]:
            resp = r["response"].replace("text: '", "").rstrip("'")
            print(f"    Response:  {resp[:250]}")
        else:
            print(f"    Response:  (none)")
        if r.get("latency_s") is not None:
            print(f"    Latency:   {r['latency_s']}s")
        if r.get("evaluation"):
            print(f"    Eval:      {r['evaluation']}")

    print(f"\n{'=' * 90}\n")


if __name__ == "__main__":
    main()
