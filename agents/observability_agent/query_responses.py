#!/usr/bin/env python3
"""Query agent responses and evaluate quality using the BigQuery Agent Analytics SDK.

Combines browsing Q&A pairs with full categorical quality evaluation.
Handles both local sub-agents and remote A2A agents by detecting
transfer_to_agent tool calls (using tool_origin) and resolving remote
agent responses via A2A_INTERACTION events or time-window matching.

Core evaluation logic lives in eval_common.py; this script provides
the CLI interface and display formatting.

Usage:
    python query_responses.py                        # evaluate last 100 sessions
    python query_responses.py --limit 50             # evaluate last 50
    python query_responses.py --session <id>         # single-session deep dive
    python query_responses.py --no-eval              # browse Q&A only (skip evaluation)
    python query_responses.py --persist              # evaluate + persist to BQ
    python query_responses.py --limit 500            # evaluate up to 500 sessions
    python query_responses.py --time_period 7d       # evaluate last 7 days
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

from agents.observability_agent.config import PROJECT_ID, DATASET_ID, TABLE_ID
from agents.observability_agent.eval_common import (
    get_client,
    resolve_trace_responses,
    run_evaluation,
)


# ---------------------------------------------------------------------------
# Category labels with emoji
# ---------------------------------------------------------------------------

def _category_label(category):
    """Human-readable label with emoji for a category."""
    labels = {
        "meaningful": "\u2705 HELPFUL",
        "false_positive": "\u274c NOT HELPFUL",
        "partial": "\u26a0\ufe0f  PARTIAL",
        "grounded": "\u2705 GROUNDED",
        "ungrounded": "\u274c NOT GROUNDED",
        "no_tool_needed": "\u2796 NO TOOL NEEDED",
        "good": "\u2705 GOOD",
        "bad": "\u274c BAD",
    }
    return labels.get(category, (category or "?").upper())


# ---------------------------------------------------------------------------
# Browse mode (--no-eval)
# ---------------------------------------------------------------------------

def run_browse(args):
    """Browse Q&A pairs without evaluation."""
    client = get_client()
    logger.info(f"Project: {PROJECT_ID}, Dataset: {DATASET_ID}, Table: {TABLE_ID}")

    from bigquery_agent_analytics import TraceFilter

    if args.session:
        traces = client.list_traces(
            filter_criteria=TraceFilter(session_ids=[args.session])
        )
        logger.info(f"Fetched session {args.session}")
    else:
        traces = client.list_traces(
            filter_criteria=TraceFilter(limit=args.limit)
        )
        logger.info(f"Fetched {len(traces)} sessions")

    results = resolve_trace_responses(client, traces)

    _print_browse_results(results)


def _print_browse_results(results):
    """Print browsed results in a readable format."""
    if not results:
        print("\n  No sessions found.")
        return

    total = len(results)
    with_response = sum(1 for r in results if r["response"])
    no_response = total - with_response
    a2a_count = sum(1 for r in results if r.get("is_a2a"))

    print(f"\n{'=' * 90}")
    summary = f"  {total} sessions  |  {with_response} with response  |  {no_response} no response"
    if a2a_count:
        summary += f"  |  {a2a_count} A2A"
    print(summary)
    print(f"{'=' * 90}")

    for r in results:
        a2a_tag = "  [A2A]" if r.get("is_a2a") else ""
        print(f"\n  [{r['time']}] {r['session_id']}{a2a_tag}")
        print(f"    Question:  {r['question']}")
        print(f"    Agent:     {r['answered_by']}")
        if r["response"]:
            resp = " ".join(r["response"].split())
            print(f"    Response:  \"{resp}\"")
        else:
            print(f"    Response:  (none)")
        if r.get("latency_s") is not None:
            print(f"    Latency:   {r['latency_s']}s")
        if r.get("evaluation"):
            print(f"    Eval:      {r['evaluation']}")

    print(f"\n{'=' * 90}\n")


# ---------------------------------------------------------------------------
# Eval mode (default)
# ---------------------------------------------------------------------------

def run_eval(args):
    """Full categorical quality evaluation with A2A response resolution."""
    model = args.model or os.getenv("EVAL_MODEL_ID", "gemini-2.5-flash")
    logger.info(f"Project: {PROJECT_ID}, Dataset: {DATASET_ID}, Table: {TABLE_ID}")
    logger.info(f"Evaluation model: {model}")
    logger.info(f"Filter: {args.time_period or 'all'}, limit {args.limit}")

    try:
        result = run_evaluation(
            time_range=args.time_period,
            limit=args.limit,
            model=model,
            persist=args.persist,
        )
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        sys.exit(1)

    _print_eval_results(result["report"], result["resolved_map"])


def _print_eval_results(report, resolved_map):
    """Print full evaluation results with per-session details and summary."""
    hr = "\u2500" * 70  # horizontal rule

    # Group sessions by usefulness category
    by_category = {"false_positive": [], "partial": [], "meaningful": []}
    for sr in report.session_results:
        for mr in sr.metrics:
            if mr.metric_name == "response_usefulness":
                cat = mr.category or "unknown"
                by_category.setdefault(cat, []).append(sr)
                break

    a2a_session_ids = {sid for sid, ctx in resolved_map.items() if ctx.get("is_a2a")}

    # --- Per-session details ---
    for cat, cat_label, limit in [
        ("false_positive", "UNHELPFUL", 10),
        ("partial", "PARTIAL", 5),
        ("meaningful", "MEANINGFUL", 3),
        ("unknown", "UNCLASSIFIED (parse errors)", 3),
    ]:
        sessions = by_category.get(cat, [])
        if not sessions:
            continue

        print(f"\n{hr}")
        print(f"  {cat_label} Sessions (showing {min(len(sessions), limit)} of {len(sessions)})")
        print(hr)

        for sr in sessions[:limit]:
            sid = sr.session_id
            ctx = resolved_map.get(sid, {})
            question = ctx.get("question", "")
            response = ctx.get("response", "")
            answered_by = ctx.get("answered_by", "")

            a2a_tag = "  [A2A]" if sid in a2a_session_ids else ""
            agent_tag = f"  \u2192 {answered_by}" if answered_by else ""
            print(f"\n  Session:     {sid}{a2a_tag}{agent_tag}")
            q = " ".join(question.split()) if question else "(none)"
            r = " ".join(response.split()) if response else "(none)"
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
                    print(f"  {'Reason:':<15}{mr.justification}")

    # --- Per-agent breakdown ---
    agent_stats = {}
    for sr in report.session_results:
        ctx = resolved_map.get(sr.session_id, {})
        agent = ctx.get("answered_by") or "unknown"
        if agent not in agent_stats:
            agent_stats[agent] = {"total": 0, "meaningful": 0, "unhelpful": 0,
                                  "partial": 0, "unclassified": 0,
                                  "is_a2a": ctx.get("is_a2a", False)}
        agent_stats[agent]["total"] += 1
        found_usefulness = False
        for mr in sr.metrics:
            if mr.metric_name == "response_usefulness":
                found_usefulness = True
                if mr.category == "meaningful":
                    agent_stats[agent]["meaningful"] += 1
                elif mr.category == "false_positive":
                    agent_stats[agent]["unhelpful"] += 1
                elif mr.category == "partial":
                    agent_stats[agent]["partial"] += 1
                else:
                    agent_stats[agent]["unclassified"] += 1
                break
        if not found_usefulness:
            agent_stats[agent]["unclassified"] += 1

    if agent_stats:
        # Compute totals for contribution percentages
        total_helpful_all = sum(s["meaningful"] for s in agent_stats.values())
        total_unhelpful_all = sum(s["unhelpful"] for s in agent_stats.values())
        total_partial_all = sum(s["partial"] for s in agent_stats.values())

        print(f"\n{hr}")
        print(f"  PER-AGENT QUALITY")
        print(hr)

        # Table header
        hdr = (f"  {'Agent':<30s} {'Sess':>4s}  {'Status':>6s}  "
               f"{'Helpful':>12s}  {'Unhelpful':>12s}  {'Partial':>7s}  "
               f"{'% of All':>8s}  {'% of All':>8s}")
        hdr2 = (f"  {'':<30s} {'':>4s}  {'':>6s}  "
                f"{'':>12s}  {'':>12s}  {'':>7s}  "
                f"{'Helpful':>8s}  {'Unhelpful':>8s}")
        print(hdr)
        print(hdr2)
        print(f"  {'─' * 98}")

        for agent, stats in sorted(agent_stats.items(), key=lambda x: -x[1]["total"]):
            total = stats["total"]
            classified = stats["meaningful"] + stats["unhelpful"] + stats["partial"]
            helpful_pct = (stats["meaningful"] / classified * 100) if classified > 0 else 0
            unhelpful_pct = (stats["unhelpful"] / classified * 100) if classified > 0 else 0
            helpful_contrib = (stats["meaningful"] / total_helpful_all * 100) if total_helpful_all > 0 else 0
            unhelpful_contrib = (stats["unhelpful"] / total_unhelpful_all * 100) if total_unhelpful_all > 0 else 0
            a2a_tag = " [A2A]" if stats["is_a2a"] else ""
            status = "\U0001f7e2" if helpful_pct >= 80 else ("\U0001f7e1" if helpful_pct >= 60 else "\U0001f534")
            agent_name = f"{agent}{a2a_tag}"
            helpful_str = f"{stats['meaningful']} ({helpful_pct:.0f}%)"
            unhelpful_str = f"{stats['unhelpful']} ({unhelpful_pct:.0f}%)"
            partial_str = str(stats["partial"])
            if stats.get("unclassified"):
                partial_str += f"+{stats['unclassified']}"

            line = (f"  {agent_name:<30s} {total:>4d}  {status:>6s}  "
                    f"{helpful_str:>12s}  {unhelpful_str:>12s}  {partial_str:>7s}  "
                    f"{helpful_contrib:>7.0f}%  {unhelpful_contrib:>7.0f}%")
            print(line)

        # Unhelpful contribution ranking (only agents with unhelpful > 0)
        unhelpful_agents = [(a, s) for a, s in agent_stats.items() if s["unhelpful"] > 0]
        if unhelpful_agents:
            print(f"\n  {'─' * 50}")
            print(f"  UNHELPFUL CONTRIBUTION RANKING (worst first):")
            print(f"  {'─' * 50}")
            for agent, stats in sorted(unhelpful_agents, key=lambda x: -x[1]["unhelpful"]):
                contrib = (stats["unhelpful"] / total_unhelpful_all * 100) if total_unhelpful_all > 0 else 0
                bar = "\u2588" * int(contrib / 2)
                a2a_tag = " [A2A]" if stats["is_a2a"] else ""
                print(f"  {agent}{a2a_tag:<25s} {stats['unhelpful']:>3d} ({contrib:>5.1f}%)  {bar}")

    # --- Summary ---
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
        print(f"  A2A sessions detected    : {len(a2a_session_ids)}")

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Query agent responses and evaluate quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           Evaluate last 100 sessions (default)
  %(prog)s --limit 50                Evaluate last 50 sessions
  %(prog)s --session <session_id>    Deep dive into a single session
  %(prog)s --no-eval                 Browse Q&A pairs without evaluation
  %(prog)s --persist                 Evaluate and persist results to BQ
  %(prog)s --time_period 7d          Evaluate last 7 days
  %(prog)s --limit 500               Evaluate up to 500 sessions
        """,
    )
    parser.add_argument("--limit", type=int, default=100,
                        help="Number of sessions (default: 100)")
    parser.add_argument("--session", type=str, default=None,
                        help="Analyze a specific session ID")

    # Eval mode (on by default; use --no-eval to browse only)
    parser.add_argument("--eval", action="store_true", default=True,
                        help="Run full quality evaluation (default: on)")
    parser.add_argument("--no-eval", dest="eval", action="store_false",
                        help="Browse Q&A pairs without evaluation")
    parser.add_argument("--time_period", type=str, default="all",
                        help="Time range for eval: 24h, 7d, or 'all' (default: all)")
    parser.add_argument("--persist", action="store_true",
                        help="Persist evaluation results to BigQuery")
    parser.add_argument("--model", type=str, default=None,
                        help="Model for evaluation (default: EVAL_MODEL_ID or gemini-2.5-flash)")

    args = parser.parse_args()

    if args.eval:
        run_eval(args)
    else:
        run_browse(args)


if __name__ == "__main__":
    main()
