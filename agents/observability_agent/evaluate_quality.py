"""Response Quality Evaluation using BigQuery Agent Analytics SDK.

Uses the SDK's CategoricalEvaluator to classify agent responses
as meaningful, partial, or unhelpful, and to check whether
responses are grounded in actual tool results.

Usage:
    python evaluate_quality.py [--time_period 7d] [--persist]
"""

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Setup path
dir_path = os.path.dirname(__file__)
sys.path.append(os.path.join(dir_path, "../.."))
sys.path.append(os.path.join(dir_path, "../../src"))

load_dotenv(os.path.join(dir_path, "../../.env"), override=True)

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from bigquery_agent_analytics import (
    Client,
    CategoricalEvaluationConfig,
    CategoricalMetricCategory,
    CategoricalMetricDefinition,
    TraceFilter,
)
from bigquery_agent_analytics.trace import parse_time_window

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quality_eval")

# --- Configuration from .env ---
PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = os.getenv("DATASET_ID")
TABLE_ID = os.getenv("TABLE_ID")
DATASET_LOCATION = os.getenv("DATASET_LOCATION", "us")
MODEL_NAME = os.getenv("EVAL_MODEL_ID", "gemini-2.5-flash")

assert PROJECT_ID, "PROJECT_ID not set"
assert DATASET_ID, "DATASET_ID not set"
assert TABLE_ID, "TABLE_ID not set"

# --- Metric Definitions ---

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

METRICS = [response_usefulness, task_grounding]


def _get_user_input(trace) -> str:
    """Extract the user's question from a trace."""
    for span in trace.spans:
        if span.event_type == "USER_MESSAGE_RECEIVED":
            c = span.content
            if isinstance(c, dict):
                return c.get("text_summary") or c.get("text") or ""
            elif c:
                return str(c)
    return ""


def _get_transfer_info(trace) -> dict:
    """Detect A2A transfer — returns remote_agent + time window, or empty dict."""
    # Strategy 1: explicit transfer_to_agent tool call
    for span in trace.spans:
        if span.event_type == "TOOL_STARTING":
            c = span.content
            if isinstance(c, dict) and c.get("tool") == "transfer_to_agent":
                remote_agent = c.get("args", {}).get("agent_name")
                if remote_agent:
                    start, end = _find_agent_window(trace, remote_agent)
                    if start and end:
                        return {"remote_agent": remote_agent,
                                "agent_start": start, "agent_end": end}

    # Strategy 2: agents with AGENT_STARTING/COMPLETED but no LLM_RESPONSE
    agents_with_response = set()
    for span in trace.spans:
        if span.event_type == "LLM_RESPONSE" and span.agent:
            c = span.content
            if isinstance(c, dict):
                resp = c.get("response", "")
                if resp and not resp.startswith("call:"):
                    agents_with_response.add(span.agent)

    seen_agents = {}
    for span in trace.spans:
        if span.event_type in ("AGENT_STARTING", "AGENT_COMPLETED") and span.agent:
            seen_agents.setdefault(span.agent, {})[span.event_type] = span.timestamp

    for agent_name, events in seen_agents.items():
        if agent_name in agents_with_response:
            continue
        start = events.get("AGENT_STARTING")
        end = events.get("AGENT_COMPLETED")
        if start and end:
            return {"remote_agent": agent_name,
                    "agent_start": start, "agent_end": end}
    return {}


def _find_agent_window(trace, agent_name):
    """Find AGENT_STARTING/COMPLETED timestamps for a given agent."""
    start = end = None
    for s in trace.spans:
        if s.agent == agent_name:
            if s.event_type == "AGENT_STARTING":
                start = s.timestamp
            elif s.event_type == "AGENT_COMPLETED":
                end = s.timestamp
    return start, end


def _resolve_remote_response(client, transfer_info) -> str:
    """Find the remote A2A agent's response via time-window query."""
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


def _fetch_session_context(client, session_ids):
    """Fetch user question and agent response for a list of session IDs.

    Handles A2A transfers by resolving remote agent responses via
    time-window matching when the SDK's trace.final_response is empty.
    """
    if not session_ids:
        return {}

    traces = client.list_traces(
        filter_criteria=TraceFilter(session_ids=session_ids, limit=len(session_ids))
    )

    context = {}
    for trace in traces:
        question = _get_user_input(trace)
        raw_response = trace.final_response or ""
        # SDK returns "call:..." tool-call responses as final_response — not real answers
        has_real_response = bool(raw_response and not raw_response.startswith("call:"))
        response = raw_response if has_real_response else ""

        # A2A workaround: resolve remote agent's response
        is_a2a = False
        if not has_real_response:
            transfer = _get_transfer_info(trace)
            if transfer:
                resolved = _resolve_remote_response(client, transfer)
                if resolved:
                    response = resolved
                    is_a2a = True

        context[trace.session_id] = {
            "question": question[:200],
            "response": response[:300],
            "is_a2a": is_a2a,
        }
    return context


def _category_label(category):
    """Human-readable label with emoji for a category."""
    labels = {
        "meaningful": "✅ HELPFUL",
        "false_positive": "❌ NOT HELPFUL",
        "partial": "⚠️  PARTIAL",
        "grounded": "✅ GROUNDED",
        "ungrounded": "❌ NOT GROUNDED",
        "no_tool_needed": "➖ NO TOOL NEEDED",
    }
    return labels.get(category, (category or "?").upper())


def main():
    parser = argparse.ArgumentParser(description="Evaluate agent response quality")
    parser.add_argument("--time_period", type=str, default="all",
                        help="Time range (e.g. 24h, 7d) or 'all' for no time filter (default: all)")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max sessions to evaluate (default: 100)")
    parser.add_argument("--persist", action="store_true", help="Persist results to BigQuery")
    parser.add_argument("--model", type=str, default=MODEL_NAME, help="Model for evaluation")
    parser.add_argument("--no-a2a-fix", action="store_true",
                        help="Disable A2A workaround (to verify upstream fix)")
    args = parser.parse_args()

    # "all" means no time filter
    if args.time_period.lower() == "all":
        args.time_period = None

    logger.info(f"Project: {PROJECT_ID}, Dataset: {DATASET_ID}, Table: {TABLE_ID}")
    logger.info(f"Evaluation model: {args.model}")
    logger.info(f"Time period: {args.time_period or 'all'}")

    # Initialize SDK client
    client = Client(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        table_id=TABLE_ID,
        location=DATASET_LOCATION,
        endpoint=args.model,
    )
    logger.info("SDK Client initialized.")

    # Build evaluation config
    cat_config = CategoricalEvaluationConfig(
        metrics=METRICS,
        endpoint=args.model,
        temperature=0.0,
        include_justification=True,
        persist_results=args.persist,
        results_table="quality_eval_results" if args.persist else None,
    )

    logger.info(f"Metrics: {[m.name for m in METRICS]}")
    logger.info(f"Persist: {args.persist}")

    # Build trace filter from time_period and limit
    start_time = parse_time_window(args.time_period) if args.time_period else None
    trace_filter = TraceFilter(
        start_time=start_time,
        limit=args.limit,
    )
    logger.info(f"Filter: {args.time_period or 'all'}, limit {args.limit}")

    # Run evaluation
    try:
        report = client.evaluate_categorical(
            config=cat_config,
            filters=trace_filter,
        )
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        sys.exit(1)

    # Fetch user questions and agent responses (with A2A workaround)
    all_session_ids = [sr.session_id for sr in report.session_results]
    logger.info(f"Fetching conversation context for {len(all_session_ids)} sessions...")
    session_context = _fetch_session_context(client, all_session_ids)

    # Count A2A sessions
    a2a_session_ids = {sid for sid, ctx in session_context.items() if ctx.get("is_a2a")}
    if a2a_session_ids:
        logger.info(f"Detected {len(a2a_session_ids)} A2A sessions (remote agent responses resolved)")

    # Re-evaluate A2A sessions that were rated unhelpful but actually have
    # a remote response (the SDK evaluator couldn't see it)
    a2a_re_eval = {}
    if not getattr(args, 'no_a2a_fix', False):
        for sr in report.session_results:
            if sr.session_id not in a2a_session_ids:
                continue
            for mr in sr.metrics:
                if mr.metric_name == "response_usefulness" and mr.category == "false_positive":
                    ctx = session_context.get(sr.session_id, {})
                    question = ctx.get("question", "")
                    response = ctx.get("response", "")
                    if question and response:
                        a2a_re_eval[sr.session_id] = (
                            f"USER_MESSAGE_RECEIVED: {question}\n"
                            f"LLM_RESPONSE: {response}"
                        )
                    break

        if a2a_re_eval:
            logger.info(f"Re-evaluating {len(a2a_re_eval)} A2A sessions with resolved responses...")
            try:
                from bigquery_agent_analytics.categorical_evaluator import classify_sessions_via_api
                re_eval_results = asyncio.run(
                    classify_sessions_via_api(a2a_re_eval, cat_config, endpoint=args.model)
                )
                # Replace the original results with re-evaluated ones
                re_eval_map = {r.session_id: r for r in re_eval_results}
                updated = []
                for sr in report.session_results:
                    if sr.session_id in re_eval_map:
                        updated.append(re_eval_map[sr.session_id])
                    else:
                        updated.append(sr)
                report.session_results = updated

                # Rebuild category distributions
                report.category_distributions = {}
                for sr in report.session_results:
                    for mr in sr.metrics:
                        dist = report.category_distributions.setdefault(mr.metric_name, {})
                        cat = mr.category or "unknown"
                        dist[cat] = dist.get(cat, 0) + 1

                logger.info(f"Re-evaluated {len(a2a_re_eval)} A2A sessions successfully")
            except Exception as e:
                logger.warning(f"A2A re-evaluation failed (using original results): {e}")
    else:
        logger.info("A2A workaround disabled (--no-a2a-fix)")

    # Group sessions by usefulness category
    by_category = {"false_positive": [], "partial": [], "meaningful": []}
    for sr in report.session_results:
        for mr in sr.metrics:
            if mr.metric_name == "response_usefulness":
                cat = mr.category or "unknown"
                by_category.setdefault(cat, []).append(sr)
                break

    # --- Print per-session details first (scroll past these) ---
    for cat, cat_label, limit in [
        ("false_positive", "UNHELPFUL", 10),
        ("partial", "PARTIAL", 5),
        ("meaningful", "MEANINGFUL", 3),
    ]:
        sessions = by_category.get(cat, [])
        if not sessions:
            continue

        print(f"\n{'─' * 70}")
        print(f"  {cat_label} Sessions (showing {min(len(sessions), limit)} of {len(sessions)})")
        print(f"{'─' * 70}")

        for sr in sessions[:limit]:
            sid = sr.session_id
            ctx = session_context.get(sid, {})
            question = ctx.get("question", "")
            response = ctx.get("response", "")

            a2a_tag = "  [A2A]" if sid in a2a_session_ids else ""
            print(f"\n  Session:     {sid}{a2a_tag}")
            q = " ".join(question[:150].split()) if question else "(none)"
            r = " ".join(response[:200].split()) if response else "(none)"
            print(f"  Question:    {q}")
            print(f"  Response:    \"{r}\"")

            metric_labels = {
                "response_usefulness": "Usefulness",
                "task_grounding": "Grounding",
            }
            for mr in sr.metrics:
                mr_label = _category_label(mr.category)
                if mr.parse_error:
                    mr_label += "  [parse error]"
                display_name = metric_labels.get(mr.metric_name, mr.metric_name)
                print(f"  {display_name + ':':<15}{mr_label}")
                if mr.justification:
                    print(f"  {'Reason:':<15}{mr.justification[:300]}")

    # --- Summaries at the very end ---
    fp_count = len(by_category.get("false_positive", []))
    partial_count = len(by_category.get("partial", []))
    meaningful_count = len(by_category.get("meaningful", []))
    total = report.total_sessions
    fp_rate = (fp_count / total * 100) if total > 0 else 0.0

    print(f"\n{'=' * 70}")
    print(f"QUALITY SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total sessions evaluated : {total}")
    print(f"  Meaningful               : {meaningful_count}")
    print(f"  Partial                  : {partial_count}")
    print(f"  Unhelpful                : {fp_count}")
    print(f"  Unhelpful rate           : {fp_rate:.1f}%")
    if a2a_session_ids:
        a2a_fix_status = "disabled (--no-a2a-fix)" if getattr(args, 'no_a2a_fix', False) else "enabled"
        print(f"  A2A sessions detected    : {len(a2a_session_ids)}  (workaround: {a2a_fix_status})")
        if a2a_re_eval:
            print(f"  A2A sessions re-evaluated: {len(a2a_re_eval)}")

    # Category distributions
    print(f"\n  Category Distributions:")
    for metric_name, dist in report.category_distributions.items():
        print(f"\n  [{metric_name}]")
        dist_total = sum(dist.values())
        for category, count in sorted(dist.items(), key=lambda x: -x[1]):
            pct = (count / dist_total * 100) if dist_total > 0 else 0.0
            bar = "#" * int(pct / 2)
            print(f"    {_category_label(category):18s}: {count:4d}  ({pct:5.1f}%) {bar}")

    # Execution details
    print(f"\n  Execution Details:")
    for key, value in report.details.items():
        v = str(value)[:120]
        print(f"    {key}: {v}")
    print(f"    created_at: {report.created_at.isoformat()}")

    print(f"{'=' * 70}")

    if fp_rate > 10:
        print(f"\n  WARNING: Unhelpful rate ({fp_rate:.1f}%) exceeds 10% threshold!")
    elif fp_rate > 0:
        print(f"\n  Unhelpful responses detected but within acceptable range.")
    else:
        print(f"\n  All responses were meaningful.")


if __name__ == "__main__":
    main()
