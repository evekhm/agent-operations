"""
Quality evaluation for agent responses using the BigQuery Agent Analytics SDK.

Runs categorical evaluation (response usefulness + task grounding) and enriches
results with session context (user messages and agent responses).
Handles both local sub-agents and remote A2A agents.

Core evaluation logic lives in eval_common.py; this module provides the
async wrapper for the report generation pipeline and AI summary generation.
"""
import asyncio
import logging
import os

from agents.observability_agent.config import (
    PROJECT_ID,
    DATASET_ID,
    TABLE_ID,
)

logger = logging.getLogger(__name__)

EVAL_MODEL_ID = os.getenv("EVAL_MODEL_ID", "gemini-2.5-flash")


async def evaluate_response_quality(time_range: str = "24h", limit: int = 1000) -> dict:
    """Runs categorical quality evaluation using the SDK.

    Evaluates agent sessions on two dimensions:
      - response_usefulness: Did the agent substantively answer the question?
      - task_grounding: Is the response backed by actual tool/data results?

    Resolves A2A remote agent responses via A2A_INTERACTION events and
    time-window matching.

    Args:
        time_range: Time window for evaluation (e.g. "24h", "7d", "all").
        limit: Maximum number of sessions to evaluate.

    Returns:
        Dict with total_sessions, category_distributions, session_results
        (enriched with user_message/agent_response/is_a2a/answered_by),
        details, created_at, a2a_sessions, or {} on failure.
    """
    try:
        from agents.observability_agent.eval_common import run_evaluation
    except ImportError:
        logger.warning("eval_common module not available — skipping quality evaluation.")
        return {}

    def _run():
        result = run_evaluation(
            time_range=time_range,
            limit=limit,
            model=EVAL_MODEL_ID,
        )
        # Remove CLI-only keys not needed by the report pipeline
        result.pop("report", None)
        result.pop("resolved_map", None)
        return result

    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)
    except Exception as e:
        logger.error(f"Quality evaluation failed: {e}")
        return {}


async def generate_quality_ai_summary(quality_data: dict) -> str:
    """Generate an AI-powered summary of the quality evaluation findings.

    Analyzes per-agent breakdown, failure patterns, and A2A impact to produce
    actionable insights. For example, it can detect that a specific agent was
    failing for most queries.

    Args:
        quality_data: The quality evaluation result dict.

    Returns:
        Markdown-formatted AI summary string, or "" on failure.
    """
    if not quality_data or quality_data.get("total_sessions", 0) == 0:
        return ""

    try:
        # Build per-agent breakdown
        agent_stats = {}
        for sr in quality_data.get("session_results", []):
            agent = sr.get("answered_by") or "unknown"
            if agent not in agent_stats:
                agent_stats[agent] = {
                    "total": 0,
                    "meaningful": 0,
                    "unhelpful": 0,
                    "partial": 0,
                    "grounded": 0,
                    "ungrounded": 0,
                    "no_tool_needed": 0,
                    "is_a2a": sr.get("is_a2a", False),
                    "example_questions": [],
                    "example_failures": [],
                }
            stats = agent_stats[agent]
            stats["total"] += 1
            user_msg = sr.get("user_message", "")

            for mr in sr.get("metrics", []):
                cat = mr.get("category", "")
                if mr.get("metric_name") == "response_usefulness":
                    if cat == "meaningful":
                        stats["meaningful"] += 1
                    elif cat == "false_positive":
                        stats["unhelpful"] += 1
                        if user_msg and len(stats["example_failures"]) < 3:
                            stats["example_failures"].append(user_msg[:150])
                    elif cat == "partial":
                        stats["partial"] += 1
                elif mr.get("metric_name") == "task_grounding":
                    if cat in ("grounded", "ungrounded", "no_tool_needed"):
                        stats[cat] += 1

            if user_msg and len(stats["example_questions"]) < 3:
                stats["example_questions"].append(user_msg[:150])

        # Build the prompt for the AI
        distributions = quality_data.get("category_distributions", {})
        total = quality_data["total_sessions"]
        a2a_count = quality_data.get("a2a_sessions", 0)

        prompt_parts = [
            "You are an AI observability analyst. Analyze the following agent "
            "quality evaluation data and produce a concise, actionable summary.",
            "",
            f"Total sessions evaluated: {total}",
            f"A2A (remote agent) sessions: {a2a_count}",
            "",
            "Overall distributions:",
        ]
        for metric, dist in distributions.items():
            prompt_parts.append(f"  {metric}: {dist}")

        # Compute totals for contribution percentages
        total_helpful_all = sum(s["meaningful"] for s in agent_stats.values())
        total_unhelpful_all = sum(s["unhelpful"] for s in agent_stats.values())

        prompt_parts.append("")
        prompt_parts.append("Per-agent breakdown (with % contribution to overall totals):")
        for agent, stats in sorted(agent_stats.items(), key=lambda x: -x[1]["total"]):
            a2a_tag = " [A2A remote]" if stats["is_a2a"] else ""
            helpful_contrib = (stats["meaningful"] / total_helpful_all * 100) if total_helpful_all > 0 else 0
            unhelpful_contrib = (stats["unhelpful"] / total_unhelpful_all * 100) if total_unhelpful_all > 0 else 0
            prompt_parts.append(
                f"  {agent}{a2a_tag}: {stats['total']} sessions \u2014 "
                f"meaningful={stats['meaningful']} ({helpful_contrib:.0f}% of all helpful), "
                f"unhelpful={stats['unhelpful']} ({unhelpful_contrib:.0f}% of all unhelpful), "
                f"partial={stats['partial']} | "
                f"grounded={stats['grounded']}, ungrounded={stats['ungrounded']}, "
                f"no_tool_needed={stats['no_tool_needed']}"
            )
            if stats["example_failures"]:
                prompt_parts.append(
                    f"    Failed on questions like: {stats['example_failures']}"
                )

        prompt_parts.extend([
            "",
            "Instructions:",
            "- Identify agents with high failure rates and explain the pattern.",
            "- Highlight any agents where the unhelpful rate exceeds 50%.",
            "- Note if A2A sessions have different quality than local ones.",
            "- For agents that consistently fail, suggest possible root causes "
            "  (e.g., missing data sources, broken tools, routing issues).",
            "- Keep the summary under 300 words. Use markdown formatting.",
            "- Start with the most critical finding first.",
            "- Do NOT repeat the raw numbers; focus on insights and patterns.",
        ])

        prompt = "\n".join(prompt_parts)

        # Call the LLM in an executor to avoid blocking the event loop
        def _call_llm():
            from google.genai import Client as GenaiClient
            client = GenaiClient()
            response = client.models.generate_content(
                model=EVAL_MODEL_ID,
                contents=prompt,
            )
            return response.text or ""

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _call_llm)

    except Exception as e:
        logger.warning(f"Failed to generate quality AI summary: {e}")
        return ""
