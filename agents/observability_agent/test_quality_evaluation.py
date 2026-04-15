#!/usr/bin/env python3
"""Standalone test for the report module's quality evaluation.

Tests the same evaluate_response_quality() function used by the report agent,
including the A2A workaround. Much faster than a full report cycle.

Usage:
    python test_quality_evaluation.py                  # default: all time
    python test_quality_evaluation.py --time_period 7d
    python test_quality_evaluation.py --time_period all
    python test_quality_evaluation.py --model gemini-2.5-pro
    python test_quality_evaluation.py --json           # raw JSON output
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time

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
logger = logging.getLogger("test_quality")


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


def print_results(data: dict):
    """Pretty-print the evaluation results."""
    if not data:
        print("\n  No results returned. Check logs above for errors.")
        return

    total = data.get("total_sessions", 0)
    distributions = data.get("category_distributions", {})
    session_results = data.get("session_results", [])
    a2a_count = data.get("a2a_sessions", 0)
    a2a_re_evaluated = data.get("a2a_re_evaluated", 0)

    # --- Per-session details ---
    by_cat = {"false_positive": [], "meaningful": [], "partial": []}
    for sr in session_results:
        for mr in sr.get("metrics", []):
            if mr.get("metric_name") == "response_usefulness":
                cat = mr.get("category", "")
                if cat in by_cat:
                    by_cat[cat].append(sr)
                break

    for cat, label, limit in [
        ("false_positive", "UNHELPFUL", 5),
        ("partial", "PARTIAL", 3),
        ("meaningful", "MEANINGFUL", 3),
    ]:
        sessions = by_cat.get(cat, [])
        if not sessions:
            continue
        print(f"\n{'─' * 70}")
        print(f"  {label} Sessions (showing {min(len(sessions), limit)} of {len(sessions)})")
        print(f"{'─' * 70}")
        for sr in sessions[:limit]:
            sid = sr.get("session_id", "?")
            user_msg = sr.get("user_message", "")
            agent_resp = sr.get("agent_response", "")

            a2a_tag = "  [A2A]" if sr.get("is_a2a") else ""
            print(f"\n  Session:     {sid}{a2a_tag}")

            q = " ".join(user_msg[:150].split()) if user_msg else "(none)"
            r = " ".join(agent_resp[:200].split()) if agent_resp else "(none)"
            print(f"  Question:    {q}")
            print(f"  Response:    \"{r}\"")

            for mr in sr.get("metrics", []):
                mr_label = _category_label(mr.get("category"))
                display_name = {
                    "response_usefulness": "Usefulness",
                    "task_grounding": "Grounding",
                }.get(mr.get("metric_name"), mr.get("metric_name", ""))
                print(f"  {display_name + ':':<15}{mr_label}")
                if mr.get("justification"):
                    print(f"  {'Reason:':<15}{mr['justification'][:300]}")

    # --- Scorecard ---
    usefulness = distributions.get("response_usefulness", {})
    grounding = distributions.get("task_grounding", {})

    meaningful = usefulness.get("meaningful", 0)
    unhelpful = usefulness.get("false_positive", 0)
    partial = usefulness.get("partial", 0)
    evaluated = meaningful + unhelpful + partial

    grounded = grounding.get("grounded", 0)
    ungrounded = grounding.get("ungrounded", 0)
    no_tool = grounding.get("no_tool_needed", 0)
    grounding_total = grounded + ungrounded + no_tool

    quality_rate = (meaningful / evaluated * 100) if evaluated else 0
    unhelpful_rate = (unhelpful / evaluated * 100) if evaluated else 0
    grounding_rate = (grounded / grounding_total * 100) if grounding_total else 0

    def status(rate, good=80, warn=60):
        return "PASS" if rate >= good else ("WARN" if rate >= warn else "FAIL")

    print(f"\n{'=' * 70}")
    print(f"  QUALITY SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total sessions evaluated : {total}")
    print(f"  Meaningful               : {meaningful}")
    print(f"  Partial                  : {partial}")
    print(f"  Unhelpful                : {unhelpful}")
    print(f"{'─' * 70}")
    print(f"  Response Quality Rate    : {quality_rate:5.1f}%  [{status(quality_rate)}]")
    print(f"  Unhelpful Rate           : {unhelpful_rate:5.1f}%  [{status(100-unhelpful_rate)}]")
    print(f"  Grounding Rate           : {grounding_rate:5.1f}%  [{status(grounding_rate)}]")
    if a2a_count:
        print(f"  A2A sessions detected    : {a2a_count}")
        if a2a_re_evaluated:
            print(f"  A2A sessions re-evaluated: {a2a_re_evaluated}")

    # Category distributions
    for metric_name, dist in distributions.items():
        label = "Response Usefulness" if metric_name == "response_usefulness" else "Task Grounding"
        dist_total = sum(dist.values())
        print(f"\n  [{label}]")
        for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
            pct = (count / dist_total * 100) if dist_total else 0
            bar = "#" * int(pct / 2)
            print(f"    {_category_label(cat):18s}: {count:4d}  ({pct:5.1f}%) {bar}")

    # Execution details
    details = data.get("details", {})
    if details:
        print(f"\n  Execution Details:")
        for k, v in details.items():
            print(f"    {k}: {str(v)[:100]}")

    print(f"\n  Created at: {data.get('created_at', '?')}")
    print(f"{'=' * 70}")


async def main():
    parser = argparse.ArgumentParser(
        description="Test the report module's quality evaluation (evaluate_response_quality)")
    parser.add_argument("--time_period", type=str, default="all",
                        help="Time range (e.g. 24h, 7d, all) (default: all)")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Max sessions to evaluate (default: 1000)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model for evaluation (default: gemini-2.5-flash)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted report")
    args = parser.parse_args()

    # Set model before importing the module (it reads EVAL_MODEL_ID at import time)
    if args.model:
        os.environ["EVAL_MODEL_ID"] = args.model

    from agents.observability_agent.agent_tools.report_generation.quality_evaluation import (
        evaluate_response_quality,
    )
    from agents.observability_agent.config import PROJECT_ID, DATASET_ID, TABLE_ID

    logger.info(f"Project: {PROJECT_ID}, Dataset: {DATASET_ID}, Table: {TABLE_ID}")
    logger.info(f"Model: {os.getenv('EVAL_MODEL_ID', 'gemini-2.5-flash')}")
    logger.info(f"Time period: {args.time_period}")
    logger.info(f"Limit: {args.limit}")

    start = time.time()
    data = await evaluate_response_quality(time_range=args.time_period, limit=args.limit)
    elapsed = time.time() - start

    logger.info(f"Evaluation completed in {elapsed:.1f}s")

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_results(data)


if __name__ == "__main__":
    asyncio.run(main())
